import test from 'node:test';
import assert from 'node:assert/strict';
import { Policy, commandIdentity, similarities, actionKey, cleanTerminal, configuration } from '../src/policy.mjs';
import { bashObservation, fingerprint } from '../src/workspace.mjs';
import { mkdtemp, writeFile, symlink } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const call = (command = 'python check.py', workdir = '.') =>
  ({ name: 'bash', arguments: { command, description: 'check', workdir }, callId: 'call1' });
const failure = { executed: true, complete: true, exitCode: 1, stdout: '', stderr: 'missing dependency' };
const S = 'sha256:initial', T = 'sha256:repaired';
const observe = (p, command = 'python check.py', result = failure) => p.observe(call(command), result, S, S);
const proposal = (p, command = 'node alternative.js') => ({ tool: 'bash', arguments: call(command).arguments,
  memory_review: 'E1 records a conditional failure.', strategy_adjustment: 'Inspect a different dependency.',
  evidence_ids: p.state.memories.slice(0, 1).map(x => x.id),
  orthogonality_proof: { dependency_dimension: 'node runtime', target_dimension: 'alternative.js', command_dimension: 'inspection' } });

test('normalize only safe whitespace and argument quoting', () => {
  assert.deepEqual(commandIdentity('python   "check.py"'), commandIdentity('python check.py'));
  assert.notDeepEqual(commandIdentity('echo "a  b"'), commandIdentity('echo "a b"'));
  assert.notDeepEqual(commandIdentity('echo "$X"'), commandIdentity('echo $X'));
  assert.notDeepEqual(commandIdentity('"python" check.py'), commandIdentity('python check.py'));
  assert.notDeepEqual(commandIdentity('a\nb'), commandIdentity('a b'));
});
test('cwd and meaningful timeout differ; description is not identity', () => {
  const a = call(); const b = structuredClone(a); b.arguments.description = 'a new route';
  assert.equal(actionKey(a), actionKey(b));
  assert.notEqual(actionKey(a), actionKey(call('python check.py', 'elsewhere')));
  b.arguments.timeoutMs = 600000;
  assert.notEqual(actionKey(a), actionKey(b));
});
test('TF-IDF identity and empty vocabulary', () => {
  assert.ok(Math.abs(similarities('python a.py', ['python a.py'])[0] - 1) < 1e-12);
  assert.deepEqual(similarities('a', ['b']), [0]);
  assert.deepEqual(similarities('python', []), []);
});
test('normal first action uses native tools', () => assert.equal(new Policy().before(call(), S).allowed, true));
test('failed repeated command is rejected but not executed', () => {
  const p = new Policy(); observe(p);
  assert.equal(p.before(call('python   check.py'), S).allowed, false);
  assert.equal(p.state.counters.observed, 1);
});
test('real repair permits the same verification command', () => {
  const p = new Policy(); observe(p);
  assert.equal(p.before(call(), T).reason, 'observed_workspace_change');
});
test('unknown state is never proof of unchanged workspace', () => {
  const p = new Policy(); observe(p);
  assert.equal(p.before(call(), 'unknown:bounded').allowed, true);
});
test('different cwd is not automatically the same failure', () => {
  const p = new Policy(); observe(p);
  assert.equal(p.before(call('python check.py', 'other'), S).allowed, true);
});
test('second identical observed failure activates exploration, unrelated failures do not', () => {
  const unrelated=new Policy();observe(unrelated);observe(unrelated,'make test');assert.equal(unrelated.state.active,false);
  const p = new Policy(); observe(p); observe(p);
  assert.equal(p.state.active, true);
  assert.equal(p.before(call('node inspect.js'), S).allowed, false);
});
test('proof is bound to exact native arguments, one-shot', () => {
  const p = new Policy(); observe(p); observe(p);
  assert.equal(p.propose(proposal(p)).accepted, true);
  assert.equal(p.before(call('node alternative.js'), S).allowed, true);
  assert.equal(p.before(call('node alternative.js'), S).allowed, false);
});
test('proof/action mismatch rejected', () => {
  const p = new Policy(); observe(p); observe(p);
  p.propose(proposal(p));
  assert.equal(p.before(call('rm important.py'), S).allowed, false);
});
test('long prose never causes a length protocol error', () => {
  const p = new Policy(); const plan = proposal(p);
  plan.memory_review = 'x'.repeat(10000);
  assert.equal(p.propose(plan).accepted, true);
});
test('invisible evidence references are rejected', () => {
  const p = new Policy(); const plan = proposal(p); plan.evidence_ids = ['E999'];
  assert.equal(p.propose(plan).accepted, false);
});
test('seven denials switch to advisory, never terminate or inject shell actions', () => {
  const p = new Policy(); observe(p);
  for (let i = 0; i < 7; i++) assert.equal(p.before(call(), S).allowed, false);
  assert.equal(p.before(call(), S).reason, 'advisory_mode');
  assert.equal(p.state.counters.observed, 1);
  observe(p); // identical failure must not re-arm rejection loop
  assert.equal(p.state.advisory, true);
});
test('read/edit tools stay native even during exploration', () => {
  const p = new Policy(); observe(p); observe(p, 'make test');
  for (const name of ['read', 'edit', 'grep', 'glob']) assert.equal(p.before({ name, arguments: {} }, S).allowed, true);
});
test('unknown, cancelled, background and truncated outcomes are not failure memories', () => {
  const p = new Policy();
  for (const change of [{ executed: false }, { complete: false }, { exitCode: null }]) observe(p, 'x', { ...failure, ...change });
  assert.equal(p.state.memories.length, 0);
});
test('a command that changes the workspace is not an unchanged failure', () => {
  const p = new Policy(); p.observe(call(), failure, S, T);
  assert.equal(p.state.memories[0].scope.startsWith('unknown:'), true);
  assert.equal(p.before(call(), T).allowed, true);
});
test('exit zero does not imply task completion', () => {
  const p = new Policy(); observe(p, 'ls', { ...failure, exitCode: 0 });
  assert.equal(p.state.memories[0].taskSuccess, null);
});
test('bounded memories and regenerated context', () => {
  const p = new Policy({ memoryCapacity: 3 });
  for (let i = 0; i < 8; i++) observe(p, `python check${i}.py`);
  assert.equal(p.state.memories.length, 3);
  assert.match(p.context(), /check7/);
  assert.match(new Policy({}, p.state).context(), /check7/);
});
test('ANSI cleaning affects excerpts only', () => {
  const p = new Policy(); observe(p, 'python check.py', { ...failure, stderr: '\x1b[31mERROR\x1b[0m' });
  assert.match(p.state.memories[0].observation, /ERROR/);
  assert.equal(p.state.memories[0].observation.includes('\x1b'), false);
  assert.equal(cleanTerminal('0%\r100%\n'), '100%\n');
});
test('adapter requires structured native exit evidence', () => {
  assert.equal(bashObservation({ isError: false, content: [{ type: 'text', text: 'PASS' }] }).complete, false);
  assert.equal(bashObservation({ isError: true }).executed, false);
});
test('disabled algorithm does not gather memory or gate', () => {
  const p = new Policy({ enabled: false }); observe(p);
  assert.equal(p.state.memories.length, 0); assert.equal(p.context(), '');
  assert.equal(p.before(call(), S).allowed, true);
});
test('invalid policy configuration fails at startup', () => {
  for (const settings of [{ maxConsecutiveRejections: 0 }, { similarityThreshold: 2 }, { memoryCapacity: -1 }])
    assert.throws(() => configuration(settings));
});
test('workspace hashing detects actual writes and returns unknown on limits', async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'kz-dsh-hash-'));
  await writeFile(path.join(root, 'test.py'), 'before');
  const a = await fingerprint(root);
  await writeFile(path.join(root, 'test.py'), 'after');
  assert.notEqual(await fingerprint(root), a);
  assert.match(await fingerprint(root, { maxBytes: 1 }), /^unknown:/);
});
