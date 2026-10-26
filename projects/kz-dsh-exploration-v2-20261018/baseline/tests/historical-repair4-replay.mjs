// Explicit, offline projection replay; intentionally excluded from *.test.mjs.
// Run: node projects/kz-dsh/tests/historical-repair4-replay.mjs
// This reads immutable audit snapshots, not credentials, remote logs or an API.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { Policy } from '../src/policy.mjs';
import { FullTask } from '../src/full-task.mjs';
import { normalizeMemorySupport } from '../src/memory.mjs';

const campaign = new URL('../../../experiment_records/longcli-kz-dsh3-20261012/', import.meta.url);
const files = ['mechanism-audit.json', 'policy-parity-audit.json'];
const bytes = await Promise.all(files.map(name => readFile(new URL(name, campaign))));
const hash = value => createHash('sha256').update(value).digest('hex');
const initialHashes = bytes.map(hash);
const [mechanism, policies] = bytes.map(value => JSON.parse(value.toString('utf8')));
const allRejections = mechanism.tasks.flatMap(task =>
  task.rejected_proposals.map(row => ({ ...row, task: task.task })));
const windowRejections = allRejections.filter(row =>
  row.reason === 'evidence_ids must reference visible task evidence.');
assert.equal(windowRejections.length, 22, 'unexpected historical reference-case inventory');

// The audit recorded the IDs/reason and membership in that task's final archive,
// but not each original proposal body or the archive at that turn. This tests
// the reference guard only: it is NOT an assertion that all original proposals
// now pass every gate or that temporal provenance was independently replayed.
const referenceProposal = ids => ({
  tool: 'bash', arguments: { command: 'offline-reference-projection-only' },
  memory_review: 'Offline reference guard projection, not a historical proposal.',
  strategy_adjustment: 'No command will be executed.', evidence_ids: ids,
});
const referencesByTask = {};
for (const row of windowRejections) {
  assert.equal(row.all_ids_in_archive, true, `${row.task}/${row.callId}: missing archive assertion`);
  assert.ok(row.ids.length && row.ids.every(id => /^E\d+$/u.test(id)));
  const realArchivedIds = [...row.ids];
  const result = new Policy().propose(referenceProposal(row.ids), { visibleEvidence: realArchivedIds });
  assert.equal(result.accepted, true, `${row.task}/${row.callId}: archived IDs rejected`);
  // Supplying only the empty display window reproduces the original guard
  // issue. The repaired host supplies known task evidence, not this window.
  assert.equal(new Policy().propose(referenceProposal(row.ids), { visibleEvidence: [] }).accepted, false);
  referencesByTask[row.task] = (referencesByTask[row.task] ?? 0) + 1;
}

// Explicit synthetic negative controls, separate from historical case counts.
let negativeControls = 0;
const known = ['E1'];
assert.equal(new Policy().propose(referenceProposal(['E404']), { visibleEvidence: known }).accepted, false);
negativeControls++;
assert.equal(new Policy().propose({ ...referenceProposal(known), memory_review: '' }, { visibleEvidence: known }).accepted, false);
negativeControls++;
const active = new Policy();
active.state.active = true;
assert.equal(active.propose(referenceProposal(known), { visibleEvidence: known }).accepted, false);
negativeControls++;

const hog = policies.find(task => task.task === 'cs61_fa24_hog');
assert.ok(hog);
const failedRows = ['E20', 'E35'].map(id => {
  const row = hog.observed_failures.find(value => value.id === id);
  assert.ok(row, `missing historical ${id}`);
  assert.equal(row.tool, 'bash');
  assert.equal(row.exitCode, 1);
  assert.equal(row.complete, true);
  assert.equal(row.failureObserved, true);
  assert.equal(row.suspect, true);
  assert.match(row.stdout + row.stderr, /Traceback/u);
  return row;
});

const tracebackResults = [];
for (const original of failedRows) {
  // Recorded complete=true describes the original native capture, NOT the
  // text stored here: the audit retained only tails (and command <=250 chars).
  // failureObserved=true in the source audit establishes executed nonzero
  // output. We do not invent an exit code, full command, full stdout, file hash
  // or causal condition. This is classification/anchor projection only.
  const observation = {
    executed: original.failureObserved, complete: original.complete,
    exitCode: original.exitCode, stdout: original.stdout, stderr: original.stderr,
    nativeToolError: original.nativeToolError,
  };
  const call = { name: 'bash', callId: `offline-projection-${original.id}`,
    arguments: { command: original.command }, commandDependencies: {} };
  const task = new FullTask({});
  const policy = new Policy();
  const { row } = task.observe(call, observation, 'unknown', 'unknown', {}, {}, policy,
    `audit-tail-projection:${original.id}`);
  assert.equal(row.complete, true);
  assert.equal(row.suspect, true);
  assert.equal(row.failureObserved, true);
  assert.equal(row.clean, false);
  assert.equal(policy.anchors().length, 1);
  assert.equal(policy.anchors()[0].outcome, 'execution_failed');
  assert.equal(policy.anchors()[0].id, row.id);
  tracebackResults.push({ historical_id: original.id, anchor: true,
    original_exit: original.exitCode, original_capture_complete: original.complete,
    replay_text: 'audit_tail_only', replay_command: original.command.length === 250 ? 'audit_prefix_only' : 'audit_command' });

  // Do not widen durable failure admission to partial/masked/unknown output.
  for (const change of [{ complete: false }, { exitCode: null }, { exitCode: 0 }, { executed: false }, { nativeToolError: true }]) {
    const control = new FullTask({}), controlPolicy = new Policy();
    control.observe(call, { ...observation, ...change }, 'unknown', 'unknown', {}, {}, controlPolicy, 'synthetic-negative-control');
    assert.equal(controlPolicy.anchors().length, 0, `${original.id}: negative control ${JSON.stringify(change)}`);
    negativeControls++;
  }
}

let quoteChannelRepairs = 0, quoteChannelInsufficient = 0;
const quoteRepairs = [];
for (const task of mechanism.tasks) {
  const evidenceRows = policies.find(value => value.task === task.task)?.observed_failures ?? [];
  for (const candidate of task.monitor_memory_candidates ?? []) {
    for (const support of candidate.support ?? []) {
      if (support.in_claimed_field !== false || support.in_stdout === support.in_stderr) continue;
      const row = evidenceRows.find(value => value.id === support.id);
      const expected = support.in_stdout ? 'stdout' : 'stderr';
      if (!row || !row[expected]?.includes(support.quote)) { quoteChannelInsufficient++; continue; }
      const projected = { support: [{ evidence_id: support.id, field: support.claimed_field, quote: support.quote }] };
      const corrected = normalizeMemorySupport(projected, { [row.id]: row });
      assert.equal(corrected.support[0].evidence_id, support.id);
      assert.equal(corrected.support[0].quote, support.quote);
      assert.equal(corrected.support[0].field, expected);
      assert.equal(corrected.support[0].declared_field, support.claimed_field);
      quoteChannelRepairs++;
      quoteRepairs.push({ task: task.task, id: support.id, from: support.claimed_field, to: expected });
      assert.throws(() => normalizeMemorySupport({ support: [{
        evidence_id: support.id, field: support.claimed_field,
        quote: 'SYNTHETIC_UNSUPPORTED_QUOTE_NOT_IN_ANY_HISTORICAL_STREAM',
      }] }, { [row.id]: row }), /exact quotes/u);
      negativeControls++;
    }
  }
}
assert.equal(quoteChannelRepairs, 1, 'unexpected historical quote-channel case inventory');

const afterHashes = await Promise.all(files.map(async name => hash(await readFile(new URL(name, campaign)))));
assert.deepEqual(afterHashes, initialHashes, 'historical audit input changed during replay');
console.log(JSON.stringify({
  status: 'passed', campaign: fileURLToPath(campaign), api_calls: 0, environment_commands: 0,
  archived_reference_guard_projections: { passed: windowRejections.length, by_task: referencesByTask,
    original_other_gate_rejections_not_replayed: allRejections.length - windowRejections.length },
  failed_anchor_projections: tracebackResults,
  quote_channel_helper_projections: { passed: quoteChannelRepairs, insufficient: quoteChannelInsufficient, repairs: quoteRepairs },
  synthetic_negative_controls_passed: negativeControls,
  historical_inputs_unchanged: true,
  limitations: [
    '22 cases replay IDs/reference guard only; full historical proposals and per-turn archive timestamps are absent.',
    'E20/E35 replay recorded exit/completeness metadata plus real text tails, not full native captures or environment execution.',
    'Monitor case replays exact quote/channel correction only; full candidate admission fields are absent.',
    'No claim that all original rejected actions are now executable, or that benchmark scores improve.',
  ],
}, null, 2));
