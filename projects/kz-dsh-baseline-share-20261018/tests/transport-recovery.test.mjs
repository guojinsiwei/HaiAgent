import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Context } from '@deepseek-ai/cordis';
import LlmRuntime, { LlmAdapter, LlmError, createUserMessage, resolveRetryPolicy } from '@deepseek-ai/dsh-llm';
import { DeepSeekAdapter, resolveAdapterOptions } from '@deepseek-ai/dsh-llm-deepseek';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import SessionStore from '@deepseek-ai/dsh-session';
import SessionProjections from '@deepseek-ai/dsh-session-projection';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import * as NativeRetry from '@deepseek-ai/dsh-llm-retry';
import * as recovery from '../src/transport-recovery.mjs';
import * as kz from '../src/plugin.mjs';

const bad = () => new LlmError(recovery.INVALID_TOOL_JSON, 'MALFORMED_RESPONSE');
const call = (id, command) => ({ type: 'tool-call', id, name: 'bash', arguments: JSON.stringify({ command }) });
const done = { type: 'text', text: 'Done.' };
const policy = maxRetries => resolveRetryPolicy({ mode: 'normal', maxRetries,
  backoff: { initialDelayMs: 1, maxDelayMs: 1, jitterRatio: 0 } }, 'offline');

class Scripted extends LlmAdapter {
  constructor(script, retry = policy(5)) { super(); this.script = script; this.retry = retry; this.requests = []; }
  providerRetryPolicy() { return this.retry; }
  async resolveModel(provider, model) { return { provider, id: model, name: model }; }
  async *stream(options) {
    const item = this.script[this.requests.length]; this.requests.push(options);
    assert.ok(item, 'unexpected extra request');
    if (item instanceof Error) {
      // A complete earlier tool block in the SAME failed response must not run.
      yield { type: 'block-start', index: 0, blockType: 'tool-call' };
      yield { type: 'block-end', index: 0, block: call('uncommitted', 'NEVER_EXECUTE') };
      throw item;
    }
    yield { type: 'block-start', index: 0, blockType: item.type };
    yield { type: 'block-end', index: 0, block: item };
    yield { type: 'usage', usage: { inputTokens: 10, outputTokens: 5 } };
    yield { type: 'finish', reason: { kind: item.type === 'text' ? 'stop' : 'tool-calls' } };
  }
}

async function host(t, { enabled = true, maxRequests = 30, withKz = true } = {}) {
  const runtime = fileURLToPath(new URL('../.runtime/', import.meta.url)); await mkdir(runtime, { recursive: true });
  const root = await mkdtemp(path.join(runtime, 'transport-r6-'));
  const workspace = path.join(root, 'task'), auditDir = path.join(root, 'audit');
  await mkdir(workspace); await writeFile(path.join(workspace, 'progress.txt'), 'retained');
  const ctx = new Context();
  for (const plugin of [LlmRuntime, SessionStore, SessionProjections, AgentRegistry]) await ctx.plugin(plugin);
  await ctx.plugin(SystemPrompt, {}); await ctx.plugin(ToolRuntime, { mode: 'native' });
  await ctx.plugin(NativeRetry);
  const protocolAudit = path.join(root, 'transport.jsonl');
  if (enabled) await ctx.plugin(recovery, { auditFile: protocolAudit });
  if (withKz) await ctx.plugin(kz, { workspace, auditDir, full: true, criticEnabled: false,
    monitorEnabled: false, maxRequests, maxTools: 50 });
  await ctx.plugin(AgentLoop, { agents: [], maxParallelToolCalls: 1 });
  const executions = [], events = [], errors = [];
  ctx.on('session/event', (_session, event) => events.push(event));
  ctx.on('agent/error', event => errors.push(event));
  ctx.tools.register({ name: 'bash', description: 'Offline tool fixture, no shell',
    parameters: { type: 'object', additionalProperties: true }, isConcurrencySafe: () => false,
    output: { schema: { type: 'object', additionalProperties: true }, render: () => [{ type: 'text', text: 'OK' }] },
    async execute(args) {
      executions.push(args.command);
      return { kind: 'foreground', exitCode: 0, timedOut: false, aborted: false, signal: null,
        stdout: { text: 'OK', truncated: false }, stderr: { text: '', truncated: false } };
    },
  });
  t.after(() => ctx.fiber.dispose());
  async function run(adapter, onAgent = () => {}) {
    ctx.llm.registerAdapter(['offline'], adapter);
    const agent = await ctx.agentLoop.create('transport-test', { provider: 'offline', model: 'deepseek-flash' }, { cwd: workspace });
    onAgent(agent);
    const idle = new Promise(resolve => {
      const stop = ctx.on('agent/status', ({ agent: who, status }) => { if (who === agent && status === 'idle') { stop(); resolve(); } });
    });
    agent.followup(createUserMessage({ content: [{ type: 'text', text: 'Complete the public fixture.' }], source: { kind: 'user' } }));
    await idle;
    const file = withKz && (await readdir(auditDir)).find(name => name.endsWith('.json'));
    const state = file ? JSON.parse(await readFile(path.join(auditDir, file), 'utf8')) : null;
    return { state, agent };
  }
  return { ctx, run, executions, events, errors, workspace, protocolAudit };
}

test('narrow classification does not swallow auth, cancellation or other malformed protocol', () => {
  assert.equal(recovery.isToolJsonFailure(bad().failure), true);
  for (const code of ['AUTH', 'QUOTA', 'TIMEOUT', 'ABORTED']) assert.equal(recovery.isToolJsonFailure({ code, message: recovery.INVALID_TOOL_JSON }), false);
  assert.equal(recovery.isToolJsonFailure({ code: 'MALFORMED_RESPONSE', message: 'DeepSeek Messages SSE contains invalid JSON' }), false);
});

test('native loop recovers one malformed response, counts retry, retains prior tool result, executes no partial blocks', { timeout: 15000 }, async t => {
  const h = await host(t); const adapter = new Scripted([call('a', 'first'), bad(), call('b', 'second'), done]);
  const { state } = await h.run(adapter);
  assert.deepEqual(h.executions, ['first', 'second']); assert.equal(h.errors.length, 0);
  assert.equal(adapter.requests.length, 4); assert.equal(state.full.usage.requests, 4);
  assert.equal(state.full.usage.tools, 2); assert.equal(state.full.observed, 2);
  const retryInput = JSON.stringify(adapter.requests[2].messages);
  assert.match(retryInput, /Earlier completed actions/); assert.match(retryInput, /first/);
  assert.ok(!retryInput.includes('NEVER_EXECUTE'));
  assert.equal(h.events.filter(e => e.type === 'protocol/retry').length, 1);
  assert.equal(await readFile(path.join(h.workspace, 'progress.txt'), 'utf8'), 'retained');
});

test('native retry allowance exhausts explicitly, not after the first malformed JSON', { timeout: 15000 }, async t => {
  const h = await host(t); const adapter = new Scripted(Array.from({ length: 6 }, bad));
  const { state } = await h.run(adapter);
  assert.equal(adapter.requests.length, 6); assert.equal(state.full.usage.requests, 6);
  assert.equal(h.executions.length, 0); assert.equal(h.errors.length, 1);
  assert.equal(h.events.filter(e => e.type === 'protocol/retry-exhausted').length, 1);
  const publicAudit = (await readFile(h.protocolAudit, 'utf8')).trim().split('\n').map(JSON.parse);
  assert.equal(publicAudit.filter(e => e.event === 'protocol/retry').length, 5);
  assert.equal(publicAudit.at(-1).event, 'protocol/retry-exhausted');
  assert.ok(!JSON.stringify(publicAudit).includes('NEVER_EXECUTE'));
  assert.equal(h.events.filter(e => e.type === 'user/message' && e.data.source?.kind === 'tool-json-recovery').length, 1);
});

test('mixed native network and JSON retries share allowance, no retry budget multiplication', { timeout: 15000 }, async t => {
  const h = await host(t); const adapter = new Scripted([bad(), new LlmError('offline timeout', 'TIMEOUT'), bad()], policy(2));
  await h.run(adapter); assert.equal(adapter.requests.length, 3);
  assert.deepEqual(h.events.filter(e => e.type === 'llm/retry').map(e => e.data.retry), [1, 2]);
  assert.equal(h.errors.length, 1);
});

test('shared request cap still blocks retry before another provider call', { timeout: 15000 }, async t => {
  const h = await host(t, { maxRequests: 2 }); const adapter = new Scripted([bad(), bad()]);
  const { state } = await h.run(adapter);
  assert.equal(adapter.requests.length, 2); assert.equal(state.full.usage.requests, 2);
  assert.equal(h.executions.length, 0); assert.equal(h.errors.length, 1);
});

test('successful steps reset local retry state; independent task errors do not pollute KZ memory', { timeout: 15000 }, async t => {
  const h = await host(t); const adapter = new Scripted([bad(), call('one', 'first'), bad(), call('two', 'second'), done], policy(1));
  const { state } = await h.run(adapter); assert.equal(h.errors.length, 0);
  assert.deepEqual(h.executions, ['first', 'second']);
  assert.deepEqual(h.events.filter(e => e.type === 'llm/retry').map(e => e.data.retry), [1, 1]);
  assert.equal(state.state.memories.filter(m => JSON.stringify(m).includes('MALFORMED_RESPONSE')).length, 0);
});

test('disabled native retries and unrelated errors are not resurrected', { timeout: 15000 }, async t => {
  const h = await host(t); const adapter = new Scripted([bad()], policy(0));
  await h.run(adapter); assert.equal(adapter.requests.length, 1); assert.equal(h.errors.length, 1);
  assert.equal(h.events.filter(e => e.type === 'llm/retry').length, 0);
});

test('repair also works in native DSH without KZ (same harness treatment for baseline)', { timeout: 15000 }, async t => {
  const h = await host(t, { withKz: false }); const adapter = new Scripted([bad(), call('fixed', 'second'), done]);
  await h.run(adapter); assert.equal(h.errors.length, 0); assert.equal(adapter.requests.length, 3);
  assert.deepEqual(h.executions, ['second']);
});

test('cancellation during queued repair never dispatches another request', { timeout: 15000 }, async t => {
  const h = await host(t); const adapter = new Scripted([bad()]);
  await h.run(adapter, agent => h.ctx.on('session/event', (session, event) => {
    if (session === agent.session && event.type === 'protocol/retry') agent.cancel({ kind: 'user' });
  }));
  assert.equal(adapter.requests.length, 1); assert.equal(h.executions.length, 0);
  assert.equal(h.events.filter(e => e.type === 'llm/retry-started').length, 0);
});

for (const [code, message] of [['AUTH', 'credentials rejected'], ['QUOTA', 'insufficient quota'],
  ['MALFORMED_RESPONSE', 'DeepSeek Messages SSE contains invalid JSON']]) {
  test(`non-tool-JSON failure ${code}/${message} retains native failure handling`, { timeout: 15000 }, async t => {
    const h = await host(t); const adapter = new Scripted([new LlmError(message, code)]);
    await h.run(adapter); assert.equal(adapter.requests.length, 1); assert.equal(h.errors.length, 1);
    assert.equal(h.events.filter(e => e.type === 'protocol/retry').length, 0);
  });
}

// Full Messages wire protocol through the official parser, no network/API.
function sse(blocks) {
  const events = [{ type: 'message_start', message: { id: 'wire-fixture', type: 'message', role: 'assistant',
    model: 'deepseek-flash', content: [], usage: { input_tokens: 10, output_tokens: 0 } } }];
  blocks.forEach((block, index) => {
    const tool = block.type === 'tool-call';
    events.push({ type: 'content_block_start', index, content_block: tool ? { type: 'tool_use', id: block.id, name: block.name, input: {} } : { type: 'text', text: '' } },
      { type: 'content_block_delta', index, delta: tool ? { type: 'input_json_delta', partial_json: block.arguments } : { type: 'text_delta', text: block.text } },
      { type: 'content_block_stop', index });
  });
  events.push({ type: 'message_delta', delta: { stop_reason: blocks.some(b => b.type === 'tool-call') ? 'tool_use' : 'end_turn' }, usage: { output_tokens: 5 } }, { type: 'message_stop' });
  return events.map(e => `event: ${e.type}\ndata: ${JSON.stringify(e)}\n\n`).join('');
}

for (const enabled of [false, true]) test(`official Messages parser reproduces and recovers the actual failure: recovery=${enabled}`, { timeout: 15000 }, async t => {
  const h = await host(t, { enabled }); const requests = [];
  const wire = [[call('completed', 'first')], [call('partial', 'NEVER_EXECUTE'), { ...call('bad', 'bad'), arguments: '{"command":' }], [call('fixed', 'second')], [done]];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'https://offline.invalid/v1/messages');
    requests.push(JSON.parse(options.body)); assert.ok(requests.length <= wire.length);
    return new Response(sse(wire[requests.length - 1]), { headers: { 'content-type': 'text/event-stream' } });
  });
  const options = resolveAdapterOptions({ baseURL: 'https://offline.invalid', thinking: 'disabled', maxTokens: 1024,
    retryPolicy: { mode: 'normal', maxRetries: 5, backoff: { initialDelayMs: 1, maxDelayMs: 1, jitterRatio: 0 } } });
  const adapter = new DeepSeekAdapter({ options: () => options, resolveAuth: async () => ({ headers: {} }), resolveUserId: () => 'offline-fixture',
    prepareExtensions: async () => ({ fields: {}, accept: async () => {} }) });
  const { state } = await h.run(adapter);
  assert.equal(requests.length, enabled ? 4 : 2, h.events.filter(e=>e.type==='turn/end').map(e=>JSON.stringify(e.data)).join('\n')); assert.equal(state.full.usage.requests, requests.length);
  assert.deepEqual(h.executions, enabled ? ['first', 'second'] : ['first']);
  assert.equal(h.errors.length, enabled ? 0 : 1);
  if (enabled) assert.match(JSON.stringify(requests[2]), /Regenerate the intended next action/);
});
