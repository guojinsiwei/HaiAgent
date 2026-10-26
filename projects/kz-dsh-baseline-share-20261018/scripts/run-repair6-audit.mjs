// Offline acceptance, no key reads/provider calls/server mutations.
import { readdirSync, readFileSync, writeFileSync, mkdirSync, mkdtempSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
const root = fileURLToPath(new URL('../', import.meta.url));
const base = path.join(root, 'audit', '2026-10-13-repair6'); mkdirSync(base, { recursive: true });
const destination = mkdtempSync(path.join(base, 'run-'));
const tests = readdirSync(path.join(root, 'tests')).filter(f => f.endsWith('.test.mjs')).map(f => 'tests/' + f);
tests.push('tests/deep-audit.mjs', 'tests/migration-round2.mjs', 'tests/migration-round3.mjs');
const tap = path.join(destination, 'regression.tap');
const run = spawnSync(process.execPath, ['--test', '--test-reporter=tap', '--test-reporter-destination=' + tap, ...tests], { cwd: root, encoding: 'utf8' });
const output = readFileSync(tap, 'utf8');
const totals = Object.fromEntries([...output.matchAll(/^# (tests|pass|fail|cancelled|skipped) (\d+)$/gm)].map(m => [m[1], Number(m[2])]));
const index = process.argv.indexOf('--python');
const python = index >= 0 ? process.argv[index + 1] : process.platform === 'win32' ? 'python' : 'python3';
const dispatch = spawnSync(python, ['-B', 'tests/test_dispatch_policy.py'], { cwd: root, encoding: 'utf8' });
writeFileSync(path.join(destination, 'dispatch.txt'), dispatch.stdout + dispatch.stderr);
const names = [...readdirSync(path.join(root, 'src')).map(f => 'src/' + f),
  ...readdirSync(path.join(root, 'config')).map(f => 'config/' + f), ...tests,
  'tests/test_dispatch_policy.py', 'scripts/prepare-config.mjs', 'scripts/run-repair6-audit.mjs',
  'deploy/longcli/runner.py', 'deploy/longcli/container_run.py', 'deploy/longcli/dispatch_policy.py',
  'package.json', 'package-lock.json', 'README.txt'];
const sha256 = Object.fromEntries(names.map(f => [f, createHash('sha256').update(readFileSync(path.join(root, f))).digest('hex')]));
const report = { time: new Date().toISOString(), candidate: 'kz-dsh 0.2.7', host: '@deepseek-ai/dsh 0.2.0-rc.2',
  platform: process.platform, node: process.version, totals, node_exit: run.status, dispatch_exit: dispatch.status,
  paid_api_calls: 0, deployed: false,
  scope: 'Official Messages parser with mocked fetch; actual native AgentLoop, ToolRuntime, native retry and KZ shared budget. Offline batch dispatcher trials; no production Docker or paid benchmark.',
  unchanged: 'Algorithm src files except new transport-recovery module unchanged. Existing native retry allowance and total task budgets retained. Frozen repair5 campaign untouched.',
  sha256 };
writeFileSync(path.join(destination, 'summary.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ ...totals, node_exit: run.status, dispatch_exit: dispatch.status, report: path.join(destination, 'summary.json') }));
if (run.stderr) console.error(run.stderr);
process.exitCode = run.status === 0 && dispatch.status === 0 ? 0 : 1;
