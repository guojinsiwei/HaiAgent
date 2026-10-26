// Offline acceptance only: no provider calls, deployment, or historical writes.
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const root=fileURLToPath(new URL('../',import.meta.url));
const destination=path.join(root,'audit','2026-10-13-repair5');
mkdirSync(destination,{recursive:true});
const tests=readdirSync(path.join(root,'tests')).filter(f=>f.endsWith('.test.mjs')).map(f=>'tests/'+f);
tests.push('tests/deep-audit.mjs','tests/migration-round2.mjs','tests/migration-round3.mjs');
const tap=path.join(destination,'regression.tap');
const run=spawnSync(process.execPath,['--test','--test-reporter=tap','--test-reporter-destination='+tap,...tests],{cwd:root,encoding:'utf8'});
const output=readFileSync(tap,'utf8');
const totals=Object.fromEntries([...output.matchAll(/^# (tests|pass|fail|cancelled|skipped) (\d+)$/gm)].map(m=>[m[1],Number(m[2])]));
let replay=null;
if(process.argv.includes('--history')) {
  const check=spawnSync(process.execPath,['tests/historical-repair4-replay.mjs'],{cwd:root,encoding:'utf8'});
  writeFileSync(path.join(destination,'historical-reference-projection.json'),check.stdout);
  replay={exit_code:check.status,report:'historical-reference-projection.json',scope:'Prior reference/memory cases only; not a performance replay.'};
  if(check.stderr)console.error(check.stderr);
}
const files=[...readdirSync(path.join(root,'src')).filter(f=>f.endsWith('.mjs')).map(f=>'src/'+f),...readdirSync(path.join(root,'config')).filter(f=>f.endsWith('.yml')).map(f=>'config/'+f),'package.json','package-lock.json','README.txt','scripts/run-repair5-audit.mjs',...(replay?['tests/historical-repair4-replay.mjs']:[]),...tests];
const sha256=Object.fromEntries(files.map(f=>[f,createHash('sha256').update(readFileSync(path.join(root,f))).digest('hex')]));
const report={date:new Date().toISOString(),candidate:'kz-dsh 0.2.6',host:'@deepseek-ai/dsh 0.2.0-rc.2',node:process.version,platform:process.platform,paid_api_calls:0,deployed:false,exit_code:run.status,totals,historical_reference_projection:replay,
  scope:'Offline units and official DSH AgentLoop/ToolRuntime with scripted model adapters; actual official DSH tool-bash/LocalBash/nativeJobs using local Git Bash, and actual Python doctest. No real model, production Linux deployment, or benchmark score validation.',
  unchanged:'DSH remains executor/compactor; backtracking frozen; shared request/tool budgets unchanged; no fatal rejection cap.',sha256};
writeFileSync(path.join(destination,'summary.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({candidate:report.candidate,...totals,exit_code:run.status,history_exit:replay?.exit_code??null,report:path.join(destination,'summary.json')}));
if(run.stderr)console.error(run.stderr);
process.exitCode=run.status!==0?(run.status??1):replay?(replay.exit_code??1):0;
