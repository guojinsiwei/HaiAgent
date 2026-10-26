import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { prepareShellReceipt, consumeShellReceipt } from '../src/shell-receipts.mjs';

const project = fileURLToPath(new URL('..', import.meta.url));
const bash = process.platform === 'win32' ? 'C:/Program Files/Git/bin/bash.exe' : '/bin/bash';
const probe = existsSync(bash) ? spawnSync(bash, ['-c', 'printf ready'], { encoding: 'utf8', timeout: 5000 }) : null;
const bashUnavailable = !probe || probe.status !== 0 || probe.stdout !== 'ready';
const real = { skip: bashUnavailable ? 'Local Bash unavailable under this sandbox; run this offline fixture suite with Bash process permission.' : false };
const prep = command => prepareShellReceipt({ command }, { enabled: true });
const receipt = (p, values = '0:-:0,0') => `\x1eKZ_PIPESTATUS_V1:${p.plan.nonce}:${values}\x1f`;
const observed = (stderr, extra = {}) => ({ executed: true, complete: true, exitCode: 0, stdout: '', stderr, ...extra });
function run(command, options = {}) {
  const { pipefail = false, ...rest } = options;
  const result = spawnSync(bash, [...(pipefail ? ['-o', 'pipefail'] : []), '-c', command], {
    cwd: project, encoding: 'utf8', timeout: 5000, ...rest,
  });
  if (result.error && result.error.code !== 'ETIMEDOUT') throw result.error;
  return observed(result.stderr ?? '', { stdout: result.stdout ?? '', exitCode: result.status,
    complete: !result.error && !result.signal, timedOut: result.error?.code === 'ETIMEDOUT', signal: result.signal });
}
async function fixture() { await mkdir(path.join(project, '.runtime'), { recursive: true }); return mkdtemp(path.join(project, '.runtime', 'shell-receipts-')); }
const quote = value => `'${value.replaceAll('\\', '/').replaceAll("'", "'\\''")}'`;

test('repair5 shell receipts are capability opt-in and never mutate original/native execution fields', () => {
  const args = Object.freeze({ command: 'false | cat', workdir: '/app', timeoutMs: 9876, run_in_background: true,
    sandbox_permissions: 'require_escalated', justification: 'fixture', stdin: 'input', unknownNativeField: { keep: true } });
  const disabled = prepareShellReceipt(args);
  assert.equal(disabled.instrumented, false); assert.equal(disabled.executionArgs, args);
  assert.equal(disabled.plan.reason, 'capability_disabled');
  const p = prepareShellReceipt(args, { enabled: true });
  assert.equal(p.instrumented, true); assert.equal(p.args, args); assert.equal(args.command, 'false | cat');
  assert.deepEqual({ ...p.executionArgs, command: args.command }, args);
  assert.equal(p.plan.originalCommand, args.command); assert.equal(p.plan.nestedProgramsVerified, false);
  assert.match(p.executionArgs.command, /^false \| cat\n/);
  assert.doesNotMatch(p.executionArgs.command, /set -[a-z]*o?\s*pipefail|\beval\b|bash -c/);
  assert.deepEqual(JSON.parse(JSON.stringify(p.plan)), p.plan);
});

test('repair5 lexer handles literal quotes and fd merge without splitting quoted pipes', () => {
  for (const command of ["printf '%s\\n' 'a|b' | cat", 'node -e "console.log(1); console.log(2)" 2>&1 | tail -n 1',
    "printf '%s' '$HOME && ; <not shell>' | cat", 'printf "hello | there"|cat']) {
    const p = prep(command); assert.equal(p.instrumented, true, command); assert.equal(p.plan.stages.length, 2);
  }
  assert.equal(prep('printf ok | cat | wc -c').plan.stages.length, 3);
  assert.notEqual(prep('false | cat').plan.nonce, prep('false | cat').plan.nonce);
});

test('repair5 unfamiliar shell syntax executes untouched with explicitly unknown stage coverage', () => {
  const commands = [
    'false; true | cat', 'false || true | cat', 'false |& cat', 'false | cat &', 'false | cat && true',
    'cd . && true && false | cat', 'set -o pipefail; false | cat', 'if true; then false | cat; fi',
    '(false | cat)', '{ false | cat; }', "echo $(false) | cat", 'echo "$HOME" | cat', 'echo `false` | cat',
    'false | cat > out', 'false | cat 2>err', 'cat <input | cat', 'cat <<EOF | cat\nEOF',
    'false | cat\ntrue', 'false | cat # comment', 'printf ok | exit 5', 'eval false | cat',
    'VAR=1 false | cat', 'false || cat', 'false |', '| cat', "printf 'open | cat", 'false',
    'cd && false | cat', 'cd - && false | cat', 'cd $HOME && false | cat', 'cd ~ && false | cat',
    'cd x* && false | cat', 'cd -P path && false | cat', 'cd . >out && false | cat',
  ];
  for (const command of commands) {
    const args = { command }, p = prepareShellReceipt(args, { enabled: true });
    assert.equal(p.instrumented, false, command); assert.equal(p.executionArgs, args);
    const result = consumeShellReceipt(p.plan, observed('', { exitCode: 0 }));
    assert.equal(result.shellStageReceipt.status, 'unknown'); assert.equal(result.shellStageReceipt.allSucceeded, null);
  }
});

test('repair5 complete native single-pipeline receipt is checked and only its own bytes are removed', () => {
  const p = prep('false | cat'), marker = receipt(p, '0:-:1,0');
  const original = observed('before\n' + marker + 'after\n');
  const row = consumeShellReceipt(p.plan, original);
  assert.equal(row.stderr, 'before\nafter\n'); assert.equal(row.receiptRaw, marker);
  assert.equal(original.stderr, 'before\n' + marker + 'after\n'); assert.equal(row.exitCode, 0);
  assert.equal(row.shellStageReceipt.status, 'verified'); assert.equal(row.shellStageReceipt.allSucceeded, false);
  assert.deepEqual(row.shellStageReceipt.stages.map(x => x.exitCode), [1, 0]);
  assert.equal(row.shellStageReceipt.scope, 'top_level_pipeline_stages_only');
  assert.equal(row.shellStageReceipt.nestedProgramsVerified, false);
});

test('repair5 native missing/partial/timeout/abort/sandbox/background-progress observations are never promoted', () => {
  const p = prep('true | cat'), marker = receipt(p);
  for (const extra of [{ complete: false }, { executed: false }, { nativeToolError: true }, { timedOut: true },
    { aborted: true }, { stopped: 'user' }, { signal: 'SIGTERM' }, { truncated: true }, { lossy: true },
    { channelUnknown: true }, { outputCoverage: 'partial_or_rendered' }, { sandbox: { denied: true } },
    { sandbox: { runnerFailed: true } }, { runnerFailed: true }, { denied: true }, { jobStage: 'progress' },
    { jobStage: 'final', jobStatus: 'failed' }, { jobStatus: 'running' }, { exitCode: null }, { exitCode: -1 }, { exitCode: 256 }]) {
    const row = consumeShellReceipt(p.plan, observed(marker, extra));
    assert.equal(row.shellStageReceipt.status, 'unknown', JSON.stringify(extra)); assert.equal(row.stderr, marker);
  }
  assert.equal(consumeShellReceipt(p.plan, observed('', { stdout: marker })).shellStageReceipt.status, 'unknown');
  assert.equal(consumeShellReceipt(p.plan, observed(marker, { jobStage: 'final', jobStatus: 'completed', outputCoverage: 'observer_stream' })).shellStageReceipt.status, 'verified');
});

test('repair5 no self-reported passed, duplicate/foreign/malformed/forged/inconsistent receipt can count as complete', () => {
  const p = prep('true | cat');
  const malformed = [
    'passed: true', receipt(prep('true | cat')), receipt(p) + receipt(p), receipt(p).slice(0, -1),
    receipt(p, '0:-:0'), receipt(p, '0:-:0,0,0'), receipt(p, '0:-:0,256'), receipt(p, '0:-:0,-1'),
    receipt(p, '0:-:0,NaN'), receipt(p, '0:-:0,00'), receipt(p, '1:-:0,0'), receipt(p, '0:0:0,0'),
    receipt(p, '0:-:-'), receipt(p, '0:-:0,0:passed'),
  ];
  for (const stderr of malformed) {
    const row = consumeShellReceipt(p.plan, observed(stderr));
    assert.equal(row.shellStageReceipt.status, 'unknown', JSON.stringify(stderr)); assert.equal(row.stderr, stderr);
  }
  for (const change of [{ nonce: 'foo' }, { version: 99 }, { prefix: 'echo hidden' }, { stages: ['true', 'false'] }, { pipeline: 'false | cat' }]) {
    assert.equal(consumeShellReceipt({ ...p.plan, ...change }, observed(receipt(p))).shellStageReceipt.status, 'unknown');
  }
  const inconsistent = consumeShellReceipt(p.plan, observed(receipt(p, '2:-:1,0'), { exitCode: 2 }));
  assert.equal(inconsistent.shellStageReceipt.status, 'unknown');
});

test('repair5 complete native stage data preserves SIGPIPE and does not invent test/task success', () => {
  const p = prep('yes | head -n 1');
  const row = consumeShellReceipt(p.plan, observed(receipt(p, '0:-:141,0')));
  assert.equal(row.shellStageReceipt.status, 'verified'); assert.equal(row.shellStageReceipt.allSucceeded, false);
  assert.deepEqual(row.shellStageReceipt.stages.map(x => x.exitCode), [141, 0]);
  assert.equal(row.checkStatus, undefined); assert.equal(row.taskSuccess, undefined); assert.equal(row.failureObserved, undefined);
});

test('repair5 real Bash captures masked first-stage failure without changing native exit or output', real, () => {
  const command = 'false | cat', p = prep(command);
  const plain = run(command), wrapped = consumeShellReceipt(p.plan, run(p.executionArgs.command));
  assert.equal(wrapped.shellStageReceipt.status, 'verified'); assert.equal(wrapped.exitCode, plain.exitCode);
  assert.equal(wrapped.stdout, plain.stdout); assert.equal(wrapped.stderr, plain.stderr);
  assert.deepEqual(wrapped.shellStageReceipt.stages.map(x => x.exitCode), [1, 0]);
});

test('repair5 real Bash snapshots all stages atomically and preserves last-stage failure', real, () => {
  for (const [command, expected] of [['false | true | cat', [1, 0, 0]], ['true | false', [0, 1]], ['true | cat', [0, 0]]]) {
    const p = prep(command), plain = run(command), row = consumeShellReceipt(p.plan, run(p.executionArgs.command));
    assert.equal(row.shellStageReceipt.status, 'verified'); assert.deepEqual(row.shellStageReceipt.stages.map(x => x.exitCode), expected);
    assert.equal(row.exitCode, plain.exitCode); assert.equal(row.stdout, plain.stdout); assert.equal(row.stderr, plain.stderr);
  }
});

test('repair5 inherited pipefail is preserved rather than added, removed or treated as receipt evidence', real, () => {
  const p = prep('false | cat');
  const plain = run(p.args.command, { pipefail: true });
  const row = consumeShellReceipt(p.plan, run(p.executionArgs.command, { pipefail: true }));
  assert.equal(plain.exitCode, 1); assert.equal(row.exitCode, 1); assert.equal(row.shellStageReceipt.status, 'verified');
  assert.deepEqual(row.shellStageReceipt.stages.map(x => x.exitCode), [1, 0]);
});

test('repair5 real quoted strings, stdin, stderr and literal 2>&1 remain byte-for-byte compatible', real, () => {
  for (const command of ["printf '%s\\n' 'a|b' 'last' | tail -n 1", 'cat | wc -c',
    `node -e "process.stderr.write('error-line'); process.stdout.write('out-line')" | cat`,
    `node -e "process.stderr.write('error-line'); process.stdout.write('out-line')" 2>&1 | cat`]) {
    const p = prep(command); assert.equal(p.instrumented, true);
    const plain = run(command, { input: 'stdin\nbytes' });
    const row = consumeShellReceipt(p.plan, run(p.executionArgs.command, { input: 'stdin\nbytes' }));
    assert.equal(row.shellStageReceipt.status, 'verified'); assert.equal(row.exitCode, plain.exitCode);
    assert.equal(row.stdout, plain.stdout, command); assert.equal(row.stderr, plain.stderr, command);
  }
});

test('repair5 real pipeline executes side effects exactly once, no hidden probe or retry', real, async () => {
  const cwd = await fixture();
  const p = prep(`node -e "require('fs').appendFileSync('once.txt', 'x')" | cat`);
  const row = consumeShellReceipt(p.plan, run(p.executionArgs.command, { cwd }));
  assert.equal(row.shellStageReceipt.status, 'verified'); assert.equal(row.shellStageReceipt.allSucceeded, true);
  assert.equal(await readFile(path.join(cwd, 'once.txt'), 'utf8'), 'x');
});

test('repair5 real literal cd prefix preserves cwd semantics and failed cd skips every pipeline stage', real, async () => {
  const root = await fixture(), child = path.join(root, 'folder with spaces'); await mkdir(child);
  for (const target of [child, path.join(root, 'not-present')]) {
    const command = `cd ${quote(target)} && pwd | cat`, p = prep(command);
    assert.equal(p.instrumented, true); assert.equal(p.plan.kind, 'cd_then_pipeline');
    const plain = run(command, { cwd: root }), row = consumeShellReceipt(p.plan, run(p.executionArgs.command, { cwd: root }));
    assert.equal(row.shellStageReceipt.status, 'verified'); assert.equal(row.exitCode, plain.exitCode);
    assert.equal(row.stdout, plain.stdout); assert.equal(row.stderr, plain.stderr);
    assert.equal(row.shellStageReceipt.prefix.exitCode, plain.exitCode);
    if (target !== child) {
      assert.equal(row.shellStageReceipt.allSucceeded, false);
      assert.deepEqual(row.shellStageReceipt.stages.map(x => [x.executed, x.exitCode]), [[false, null], [false, null]]);
    }
  }
});

test('repair5 literal cd parsing and prefix receipt validations cannot invent skipped stage exit codes', () => {
  const p = prep('cd -- "folder x" && false | cat'); assert.equal(p.instrumented, true);
  const failed = consumeShellReceipt(p.plan, observed(receipt(p, '1:1:-'), { exitCode: 1 }));
  assert.equal(failed.shellStageReceipt.status, 'verified'); assert.equal(failed.shellStageReceipt.stages[0].executed, false);
  for (const values of ['0:-:0,0', '0:0:-', '0:1:-', '0:1:0,0', '0:0:0']) {
    assert.equal(consumeShellReceipt(p.plan, observed(receipt(p, values))).shellStageReceipt.status, 'unknown', values);
  }
});

test('repair5 real background-style observation accepts receipt only after native final completion', real, async () => {
  const p = prep('sleep 0.15 | cat');
  const child = spawn(bash, ['-c', p.executionArgs.command], { cwd: project, stdio: ['ignore', 'pipe', 'pipe'] });
  let stdout = '', stderr = ''; child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
  child.stdout.on('data', chunk => { stdout += chunk; }); child.stderr.on('data', chunk => { stderr += chunk; });
  const progress = consumeShellReceipt(p.plan, observed(stderr, { stdout, complete: false, exitCode: null, jobStage: 'progress', jobStatus: 'running' }));
  assert.equal(progress.shellStageReceipt.status, 'unknown');
  const exitCode = await new Promise((resolve, reject) => { child.on('error', reject); child.on('close', resolve); });
  const final = consumeShellReceipt(p.plan, observed(stderr, { stdout, exitCode, jobStage: 'final', jobStatus: 'completed', outputCoverage: 'observer_stream' }));
  assert.equal(final.shellStageReceipt.status, 'verified'); assert.equal(final.shellStageReceipt.allSucceeded, true);
});

test('repair5 real timeout remains an incomplete command, with no automatic execution restart', real, () => {
  const p = prep('sleep 2 | cat'), native = run(p.executionArgs.command, { timeout: 100 });
  assert.equal(native.timedOut, true); assert.equal(native.complete, false);
  const row = consumeShellReceipt(p.plan, native);
  assert.equal(row.shellStageReceipt.status, 'unknown'); assert.equal(row.shellStageReceipt.allSucceeded, null);
});

test('repair5 original cd conditional preserves inherited errexit and ERR-trap semantics', real, async () => {
  const root = await fixture(), startup = path.join(root, 'bash-startup');
  await writeFile(startup, `trap 'printf "fixture-ERR:%s\\n" "$?" >&2' ERR\nset -e\n`);
  const env = { ...process.env, BASH_ENV: startup.replaceAll('\\', '/') };
  const commands = [
    `cd ${quote(path.join(root, 'missing'))} && true | cat`,
    `cd ${quote(root)} && false | cat`,
    `cd ${quote(root)} && true | false`,
    `cd ${quote(root)} && true | cat`,
  ];
  for (const command of commands) for (const pipefail of [false, true]) {
    const p = prep(command), plain = run(command, { env, pipefail });
    const wrapped = consumeShellReceipt(p.plan, run(p.executionArgs.command, { env, pipefail }));
    assert.equal(wrapped.stdout, plain.stdout, command); assert.equal(wrapped.stderr, plain.stderr, command);
    assert.equal(wrapped.exitCode, plain.exitCode, command);
    if (/fixture-ERR/u.test(plain.stderr)) assert.equal(wrapped.shellStageReceipt.status, 'unknown', 'errexit can exit before telemetry; missing receipt is honest unknown');
  }
});

test('repair5 inherited function named exit cannot replace native pipeline exit semantics', real, async () => {
  const root = await fixture(), startup = path.join(root, 'bash-startup');
  await writeFile(startup, `exit() { printf 'user-exit-function'; return 4; }\n`);
  const env = { ...process.env, BASH_ENV: startup.replaceAll('\\', '/') };
  const command = 'false | cat', p = prep(command), plain = run(command, { env });
  const wrapped = consumeShellReceipt(p.plan, run(p.executionArgs.command, { env }));
  assert.equal(wrapped.shellStageReceipt.status, 'verified'); assert.equal(wrapped.stdout, plain.stdout);
  assert.equal(wrapped.stderr, plain.stderr); assert.equal(wrapped.exitCode, plain.exitCode);
});
