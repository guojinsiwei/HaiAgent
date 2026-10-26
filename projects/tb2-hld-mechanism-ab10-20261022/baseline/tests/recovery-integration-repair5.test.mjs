import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Context } from '@deepseek-ai/cordis';
import LlmRuntime, { LlmAdapter, createUserMessage } from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import SessionStore from '@deepseek-ai/dsh-session';
import SessionProjections from '@deepseek-ai/dsh-session-projection';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import * as plugin from '../src/plugin.mjs';

// These fixtures use the real DSH AgentLoop, tool middleware, session projection
// and shared-budget hooks. The adapter and native tool DTOs are offline scripted
// values: no model API, shell process, network or benchmark grader is invoked.
const nativeArgs = { command: 'python check.py', description: 'public test' };
const strategy = (extra = {}) => ({
  tool: 'bash', arguments: nativeArgs, execute: true,
  memory_review: 'No applicable task memory is supplied.',
  strategy_adjustment: 'Run a concrete public check.', evidence_ids: [], ...extra,
});
const rejected = index => ({ name: 'kz_strategy', args: strategy({
  arguments: { command: `python check.py --case=${index}` }, evidence_ids: ['E999'],
}) });
const dto = exitCode => ({
  kind: 'foreground', exitCode, timedOut: false, aborted: false, signal: null,
  stdout: { text: exitCode ? '' : 'public check passed', truncated: false },
  stderr: { text: exitCode ? 'AssertionError: fixture public check failed' : '', truncated: false },
});

class RecoveryAdapter extends LlmAdapter {
  constructor(script, { injectControlMemory = false } = {}) {
    super(); this.script = script; this.injectControlMemory = injectControlMemory;
    this.requests = []; this.roles = []; this.solver = 0;
  }
  async resolveModel(provider, model) { return { provider, id: model, name: model }; }
  async *stream(options) {
    this.requests.push(options); let block;
    if (options.system) {
      const payload = JSON.parse(options.messages[0].content[0].text); let value;
      if (payload.question) {
        this.roles.push({ role: 'advisor', payload });
        const ids = payload.handover.failed_attempts_and_trigger_evidence.map(row => row.id);
        value = { alternatives: [{ hypothesis: 'The proposal cites an unavailable observation.',
          check: 'Read the public task file using the native read tool.',
          difference: 'Inspect available evidence instead of repeating an unexecuted proposal.',
          evidence_ids: ids.slice(-2) }] };
      } else {
        this.roles.push({ role: 'monitor', payload });
        const ids = Object.keys(payload.control_events);
        value = { verdict: 'stalled', reason: 'Multiple proposals were rejected before environment execution.',
          evidence_ids: [], control_ids: ids.slice(-3),
          next_check: 'Read the public task file and use only actually observed E IDs.', memories: [] };
        if (this.injectControlMemory) value.memories.push({
          kind: 'blocker', conclusion: 'This deliberately invalid candidate claims a command failed.',
          condition: 'Synthetic negative control: a rejected proposal is not an executed failure.',
          targets: ['check.py'], evidence_ids: [ids.at(-1)],
          support: [{ evidence_id: ids.at(-1), field: 'stderr', quote: payload.control_events[ids.at(-1)].reason }],
        });
      }
      block = { type: 'text', text: JSON.stringify(value) };
    } else {
      const step = this.script[this.solver++];
      assert.ok(step, 'unexpected Solver request beyond the offline scenario');
      block = typeof step === 'string' ? { type: 'text', text: step }
        : { type: 'tool-call', id: `recovery-r5-${this.solver}`, name: step.name, arguments: JSON.stringify(step.args) };
    }
    yield { type: 'block-start', index: 0, blockType: block.type };
    if (block.type === 'text') yield { type: 'text-delta', index: 0, text: block.text };
    else yield { type: 'tool-call-delta', index: 0, id: block.id, name: block.name, argumentsDelta: block.arguments };
    yield { type: 'block-end', index: 0, block };
    yield { type: 'usage', usage: { inputTokens: 10, outputTokens: 5 } };
    yield { type: 'finish', reason: { kind: block.type === 'text' ? 'stop' : 'tool-calls' } };
  }
}

async function host(t, config = {}) {
  const runtime = fileURLToPath(new URL('../.runtime/', import.meta.url)); await mkdir(runtime, { recursive: true });
  const base = await mkdtemp(path.join(runtime, 'recovery-integration-r5-'));
  const workspace = path.join(base, 'task'), auditDir = path.join(base, 'audit');
  await mkdir(workspace); await writeFile(path.join(workspace, 'check.py'), '# stable public task source\n');
  const ctx = new Context();
  await ctx.plugin(LlmRuntime); await ctx.plugin(SessionStore); await ctx.plugin(SessionProjections); await ctx.plugin(AgentRegistry);
  await ctx.plugin(SystemPrompt, {}); await ctx.plugin(ToolRuntime, { mode: 'native' });
  await ctx.plugin(plugin, { workspace, auditDir, full: true, criticEnabled: false,
    maxRequests: 20, maxTools: 50, monitorCooldown: 3, ...config });
  await ctx.plugin(AgentLoop, { agents: [], maxParallelToolCalls: 1 });
  let executions = 0;
  ctx.tools.register({ name: 'bash', description: 'Offline scripted public-check receipt; never executes a process',
    parameters: { type: 'object', additionalProperties: true }, isConcurrencySafe: () => false,
    output: { schema: { type: 'object', additionalProperties: true }, render: (_args, value) => [{ type: 'text', text: JSON.stringify(value) }] },
    execute: async () => { executions++; return dto(config.fixtureExitCode ?? 0); } });
  const state = async () => {
    const file = (await readdir(auditDir)).find(name => name.endsWith('.json'));
    assert.ok(file, 'task checkpoint not persisted');
    return JSON.parse(await readFile(path.join(auditDir, file), 'utf8'));
  };
  const events = async () => {
    const files = (await readdir(auditDir)).filter(name => name.endsWith('.jsonl'));
    return (await Promise.all(files.map(name => readFile(path.join(auditDir, name), 'utf8'))))
      .flatMap(text => text.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)));
  };
  async function run(script, adapterOptions) {
    const adapter = new RecoveryAdapter(script, adapterOptions);
    ctx.llm.registerAdapter(['recovery-fixture'], adapter);
    const agent = await ctx.agentLoop.create('recovery-r5', { provider: 'recovery-fixture', model: 'offline' }, { cwd: workspace });
    const idle = new Promise(resolve => {
      const dispose = ctx.on('agent/status', ({ agent: who, status }) => { if (who === agent && status === 'idle') { dispose(); resolve(); } });
    });
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'Implement the public task and verify check.py.' }], source: { kind: 'user' } }));
    await idle;
    return adapter;
  }
  t.after(() => ctx.fiber.dispose());
  return { ctx, state, events, run, executions: () => executions };
}

test('R5 integration: pure proposal refusals reach Monitor and Advisor as R records without inventing E or failure memory', { timeout: 15000 }, async t => {
  const h = await host(t, { maxRequests: 12 });
  const adapter = await h.run([rejected(1), rejected(2), rejected(3), 'Partial delivery: no command was executed.'], { injectControlMemory: true });
  const saved = await h.state(), events = await h.events();
  assert.equal(h.executions(), 0); assert.equal(saved.full.observed, 0); assert.deepEqual(saved.full.evidence, {});
  assert.equal(saved.full.recoveryClock.steps, 3); assert.equal(saved.full.recoveryClock.rejections, 3);
  assert.equal(saved.full.recoveryClock.executions, 0);
  const monitor = adapter.roles.find(row => row.role === 'monitor'), advisor = adapter.roles.find(row => row.role === 'advisor');
  assert.ok(monitor); assert.ok(advisor);
  assert.deepEqual(Object.keys(monitor.payload.evidence), []);
  assert.deepEqual(Object.keys(monitor.payload.control_events), ['R1', 'R2', 'R3']);
  assert.deepEqual(saved.full.monitor.evidence_ids, []);
  assert.deepEqual(saved.full.monitor.control_ids, ['R1', 'R2', 'R3']);
  const handed = advisor.payload.handover.failed_attempts_and_trigger_evidence;
  assert.ok(handed.length >= 2);
  for (const row of handed) { assert.match(row.id, /^R\d+$/u); assert.equal(row.executed, false); assert.equal(row.exitCode, null); assert.equal(row.controlEvent, true); }
  assert.deepEqual(saved.full.memory.items, []); assert.deepEqual(saved.state.memories, []);
  assert.ok(saved.full.notices.some(value => /monitor memory rejected/u.test(value)));
  assert.equal(saved.full.usage.requests, 6); assert.equal(adapter.requests.length, 6);
  assert.deepEqual(saved.full.usage.roles, { solver: 4, monitor: 1, advisor: 1 });
  assert.equal(events.filter(row => row.event === 'monitor_unavailable' || row.event === 'advisor_unavailable').length, 0);
});

test('R5 integration: unexecuted KZ rejections advance Advisor cooldown without additional environment output', { timeout: 15000 }, async t => {
  const h = await host(t, { monitorEnabled: false, advisorCooldownTools: 5, maxRequests: 20 });
  const adapter = await h.run([...Array.from({ length: 8 }, (_, i) => rejected(i + 1)), 'Partial work retained.']);
  const saved = await h.state(), events = await h.events(); let clock = 0; const triggerClocks = [];
  for (const row of events) {
    if (row.event === 'recovery_rejection') clock = row.clock;
    if (row.event === 'advisor_trigger') triggerClocks.push(clock);
  }
  assert.deepEqual(triggerClocks, [3, 8]);
  assert.equal(adapter.roles.filter(row => row.role === 'advisor').length, 2);
  assert.ok(events.some(row => row.event === 'advisor_skipped' && row.reason === 'cooldown'));
  assert.equal(saved.full.lastAdvisorClock, 8); assert.equal(saved.full.recoveryClock.steps, 8);
  assert.equal(saved.full.recoveryClock.rejections, 8); assert.equal(saved.full.observed, 0); assert.equal(h.executions(), 0);
  assert.equal(saved.full.usage.requests, 11); assert.ok(saved.full.usage.requests <= 20);
});

test('R5 integration: DSH host permission denials are not KZ semantic failures or recovery-clock rejections', { timeout: 15000 }, async t => {
  const h = await host(t);
  h.ctx.on('tools/pre-execute', async (exec, next) => exec.name === 'bash' ? { kind: 'deny', reason: 'fixture host permission denied' } : next());
  const adapter = await h.run([{ name: 'bash', args: nativeArgs }, { name: 'bash', args: nativeArgs }, { name: 'bash', args: nativeArgs }, 'Permission required; no execution claimed.']);
  const saved = await h.state(), events = await h.events();
  assert.equal(h.executions(), 0); assert.equal(saved.full.usage.tools, 0);
  assert.equal(saved.full.recoveryClock.steps, 0); assert.equal(saved.full.recoveryClock.rejections, 0);
  assert.deepEqual(saved.full.evidence, {}); assert.deepEqual(saved.full.memory.items, []); assert.deepEqual(saved.state.memories, []);
  assert.equal(saved.state.counters.denied, 0); assert.equal(adapter.roles.length, 0);
  assert.equal(events.filter(row => row.event === 'recovery_rejection').length, 0);
  assert.equal(events.filter(row => row.event === 'tool_not_executed').length, 3);
});

test('R5 integration: declaration and atomic child gates count once, not once for every wrapper layer', { timeout: 15000 }, async t => {
  const h = await host(t, { fixtureExitCode: 1, monitorEnabled: false });
  await h.run([
    { name: 'bash', args: nativeArgs },
    { name: 'kz_strategy', args: strategy({ execute: false, evidence_ids: ['E1'] }) },
    { name: 'kz_strategy', args: strategy({ evidence_ids: ['E1'] }) },
    { name: 'kz_strategy', args: strategy({ evidence_ids: ['E999'] }) },
    'Partial work retained after observed failure and two rejected proposals.',
  ]);
  const saved = await h.state(), events = await h.events();
  assert.equal(h.executions(), 1); assert.equal(saved.full.observed, 1);
  assert.equal(saved.full.recoveryClock.steps, 3); assert.equal(saved.full.recoveryClock.executions, 1); assert.equal(saved.full.recoveryClock.rejections, 2);
  assert.deepEqual(saved.full.recoveryClock.controls.map(row => row.callId), ['recovery-r5-3:action', 'recovery-r5-4']);
  assert.deepEqual(saved.full.recoveryClock.controls.map(row => row.kind), ['gate', 'proposal']);
  assert.equal(events.filter(row => row.event === 'recovery_rejection').length, 2);
  assert.equal(events.filter(row => row.event === 'strategy_execution_receipt').length, 1);
  assert.deepEqual(Object.keys(saved.full.evidence), ['E1']);
  assert.equal(saved.full.usage.tools, 4, 'one native execution plus three metadata wrappers; denied child not admitted');
});

for (const maxRequests of [4, 5]) test(`R5 integration: ${maxRequests}-request shared cap reserves the final Solver request without hidden auxiliary allowance`, { timeout: 15000 }, async t => {
  const h = await host(t, { maxRequests });
  const adapter = await h.run([rejected(1), rejected(2), rejected(3), 'Final partial delivery within the original budget.']);
  const saved = await h.state(), events = await h.events();
  assert.equal(adapter.solver, 4); assert.equal(saved.full.usage.roles.solver, 4);
  assert.equal(saved.full.usage.requests, maxRequests); assert.equal(adapter.requests.length, maxRequests);
  assert.equal(adapter.roles.filter(row => row.role === 'monitor').length, maxRequests - 4);
  assert.equal(adapter.roles.filter(row => row.role === 'advisor').length, 0);
  assert.ok(events.some(row => row.event === 'advisor_skipped' && row.reason === 'shared_budget_reserve_solver'));
  assert.equal(saved.full.recoveryClock.rejections, 3); assert.equal(h.executions(), 0);
});
