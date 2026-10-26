import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, mkdtemp, readdir, readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Context } from '@deepseek-ai/cordis';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import LlmRuntime from '@deepseek-ai/dsh-llm';
import LocalSubprocess from '@deepseek-ai/dsh-subprocess-local';
import LocalBash from '@deepseek-ai/dsh-bash-local';
import LocalJobs from '@deepseek-ai/dsh-jobs-local';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import * as ShellEnv from '@deepseek-ai/dsh-shell-env';
import * as BashTool from '@deepseek-ai/dsh-tool-bash';
import { Session } from '@deepseek-ai/dsh-session';
import { createScope } from '@deepseek-ai/dsh-scope';
import { actionKey } from '../src/policy.mjs';
import * as plugin from '../src/plugin.mjs';

const runtime = fileURLToPath(new URL('../.runtime/', import.meta.url));
const bash = process.platform === 'win32' ? 'C:/Program Files/Git/bin/bash.exe' : '/bin/bash';
const probe = existsSync(bash) ? spawnSync(bash, ['-c', 'printf ready'], { encoding: 'utf8', timeout: 5000 }) : null;
const real = { timeout: 20000, skip: !probe || probe.status !== 0 || probe.stdout !== 'ready' ? 'Local Bash not executable in this sandbox.' : false };

// Keep the official DSH executor/lifecycle. Only resolve Bash's binary path for
// Windows, where `bash` otherwise selects the unrelated system WSL launcher.
class FixtureBash extends LocalBash {
  async execute(spec) { return this.executeArgv(spec, [bash, '-c', spec.command]); }
}
async function fixture(t, { background = false, shellReceipts = true } = {}) {
  await mkdir(runtime, { recursive: true });
  const base = await mkdtemp(path.join(runtime, 'shell-integration-repair5-')), workspace = path.join(base, 'task'), auditDir = path.join(base, 'audit');
  await mkdir(workspace);
  const ctx = new Context();
  await ctx.plugin(LlmRuntime); await ctx.plugin(SystemPrompt, {}); await ctx.plugin(ToolRuntime, { mode: 'native' });
  await ctx.plugin(LocalSubprocess);
  await ctx.plugin(FixtureBash, { cwd: workspace, timeoutMs: 5000, maxTimeoutMs: 10000, maxOutputBytes: 64000 });
  await ctx.plugin(ShellEnv, { dshHome: path.join(base, 'dsh') });
  if (background) { await ctx.plugin(AgentRegistry); await ctx.plugin(LocalJobs, {}); ctx.jobs.attachController('shell-integration-fixture'); }
  await ctx.plugin(BashTool, { enableRunInBackground: background, promoteOnTimeout: false });
  await ctx.plugin(plugin, { workspace, auditDir, full: true, shellReceipts, monitorEnabled: false, criticEnabled: false });
  t.after(() => ctx.fiber.dispose());
  let executions = 0, serial = 0; const nativeSpecs = [], permissions = [], finalArgs = [];
  const executeShell = ctx.shell.execute.bind(ctx.shell);
  ctx.shell.execute = async spec => { executions++; nativeSpecs.push({ command: spec.command, workdir: spec.workdir, timeoutMs: spec.timeoutMs }); return executeShell(spec); };
  ctx.on('tools/pre-execute', async (exec, next) => { if (exec.name === 'bash') permissions.push(structuredClone(exec.arguments)); return next(); });
  ctx.on('tools/result', (exec) => { if (exec.name === 'bash') finalArgs.push(structuredClone(exec.arguments)); });
  if (background) ctx.tools.register({ name: 'job_output', description: 'Offline observer of the real native registry', parameters: { type: 'object', additionalProperties: true },
    output: { schema: { type: 'object', additionalProperties: true }, render: (_a, value) => [{ type: 'text', text: value.text }] },
    execute: args => { const value = ctx.jobs.read(args.job_id); return { job: value.job, text: value.chunks.map(x => x.text).join('') }; } });
  const session = Session.create('shell-integration-repair5'), agent = { id: session.id, session, ctx: createScope(ctx, {}).ctx };
  if (background) await ctx.agents.register(agent);
  const execute = (name, args) => ctx.tools.execute({ name, arguments: args, callId: `real-${++serial}`, agent, signal: new AbortController().signal });
  const state = async () => {
    const files = await readdir(auditDir); const name = files.find(x => x.endsWith('.json'));
    return name ? JSON.parse(await readFile(path.join(auditDir, name), 'utf8')) : null;
  };
  const events = async () => (await Promise.all((await readdir(auditDir)).filter(x => x.endsWith('.jsonl')).map(x => readFile(path.join(auditDir, x), 'utf8'))))
    .flatMap(text => text.trim().split('\n').filter(Boolean).map(line => JSON.parse(line)));
  const args = command => ({ command, description: 'Offline shell receipt integration fixture', workdir: workspace, timeoutMs: 4000 });
  return { ctx, agent, execute, state, events, args, permissions, finalArgs, nativeSpecs, executions: () => executions };
}

test('repair5 official DSH Bash keeps permission/action identity original and records real upstream failure', real, async t => {
  const f = await fixture(t), args = f.args('false | cat');
  const result = await f.execute('bash', args);
  assert.equal(result.isError, false, JSON.stringify(result)); assert.equal(result.value.exitCode, 0);
  assert.equal(f.executions(), 1); assert.deepEqual(f.permissions, [args]); assert.deepEqual(f.finalArgs, [args]);
  assert.notEqual(f.nativeSpecs[0].command, args.command); assert.equal(f.nativeSpecs[0].workdir, args.workdir); assert.equal(f.nativeSpecs[0].timeoutMs, args.timeoutMs);
  assert.match(result.value.stderr.text, /KZ_PIPESTATUS_V1:/, 'original native result retains machine receipt in raw audit');
  const saved = await f.state(), row = saved.full.evidence.E1;
  assert.equal(row.command, args.command); assert.deepEqual(row.arguments, args); assert.equal(row.key, actionKey({ name: 'bash', arguments: args }));
  assert.equal(row.shellStageReceipt.status, 'verified'); assert.deepEqual(row.shellStageReceipt.stages.map(x => x.exitCode), [1, 0]);
  assert.equal(row.clean, false); assert.equal(row.failureObserved, false); assert.equal(row.taskSuccess, null); assert.equal(row.stderr, '');
  assert.equal(saved.state.memories.length, 0); assert.equal(saved.full.memory.items.length, 0);
  assert.equal((await f.events()).filter(x => x.event === 'shell_receipt_instrumented').length, 1);
});

test('repair5 official DSH all-zero pipeline is clean execution but not a task/public-check pass', real, async t => {
  const f = await fixture(t); await f.execute('bash', f.args("printf '%s' ok | cat"));
  const saved = await f.state(), row = saved.full.evidence.E1;
  assert.equal(row.stdout, 'ok'); assert.equal(row.clean, true); assert.equal(row.checkStatus, 'unknown'); assert.equal(row.taskSuccess, null);
  assert.deepEqual(row.shellStageReceipt.stages.map(x => x.exitCode), [0, 0]);
  assert.equal(saved.state.memories[0].outcome, 'execution_succeeded'); assert.equal(saved.state.memories[0].taskSuccess, null);
});

test('repair5 original host denial prevents every native process and creates no execution evidence', real, async t => {
  const f = await fixture(t), args = f.args('false | cat');
  f.ctx.on('tools/pre-execute', async (exec, next) => exec.name === 'bash' ? { kind: 'deny', reason: 'fixture host permission denial' } : next());
  const result = await f.execute('bash', args);
  assert.equal(result.isError, true); assert.equal(f.executions(), 0); assert.deepEqual(f.finalArgs, [args]);
  const saved = await f.state(); assert.deepEqual(saved.full.evidence, {}); assert.equal(saved.state.memories.length, 0);
  assert.equal((await f.events()).filter(x => x.event === 'shell_receipt_instrumented').length, 0);
});

test('repair5 unsupported compound syntax stays unchanged and cannot certify pipeline success', real, async t => {
  const f = await fixture(t), args = f.args('false; true | cat');
  assert.equal((await f.execute('bash', args)).isError, false); assert.equal(f.nativeSpecs[0].command, args.command);
  const saved = await f.state(), row = saved.full.evidence.E1;
  assert.equal(row.complete, true); assert.equal(row.shellStageReceipt.status, 'unknown'); assert.equal(row.clean, false);
  assert.equal(row.shellStageCoverage, 'unknown_composite_statuses'); assert.equal(row.taskSuccess, null);
  assert.equal(saved.state.memories.some(x => x.outcome === 'execution_succeeded'), false);
});

test('repair5 official background job receives pipeline statuses only on final real registry receipt', real, async t => {
  const f = await fixture(t, { background: true }), args = { ...f.args('sleep 0.2 | cat'), run_in_background: true };
  const launched = await f.execute('bash', args); assert.equal(launched.isError, false, JSON.stringify(launched));
  assert.equal(launched.value.kind, 'background'); assert.equal(f.executions(), 1);
  let saved = await f.state();
  assert.ok(Object.values(saved.full.evidence).every(x => x.shellStageReceipt.status !== 'verified'));
  await f.ctx.jobs.wait(launched.value.jobId, 5000, f.agent.id);
  await f.execute('job_output', { job_id: launched.value.jobId });
  saved = await f.state(); const finals = Object.values(saved.full.evidence).filter(x => x.jobStage === 'final');
  assert.equal(finals.length, 1); assert.equal(finals[0].complete, true); assert.equal(finals[0].shellStageReceipt.status, 'verified');
  assert.deepEqual(finals[0].shellStageReceipt.stages.map(x => x.exitCode), [0, 0]);
  assert.equal(finals[0].command, args.command); assert.equal(finals[0].taskSuccess, null); assert.equal(f.executions(), 1);
  assert.doesNotMatch(finals[0].stderr, /KZ_PIPESTATUS_V1/);
  await f.execute('job_output', { job_id: launched.value.jobId });
  assert.equal(Object.values((await f.state()).full.evidence).filter(x => x.jobStage === 'final').length, 1);
});
