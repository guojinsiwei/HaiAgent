// Offline, reproducible acceptance run. No provider calls or deployment.
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const root=fileURLToPath(new URL('../',import.meta.url));
const destination=path.join(root,'audit','2026-10-13-repair4');
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
  writeFileSync(path.join(destination,'historical-replay.json'),check.stdout);
  replay={exit_code:check.status,report:'historical-replay.json'};
  if(check.stderr)console.error(check.stderr);
}
const files=[...readdirSync(path.join(root,'src')).filter(f=>f.endsWith('.mjs')).map(f=>'src/'+f),...readdirSync(path.join(root,'config')).filter(f=>f.endsWith('.yml')).map(f=>'config/'+f),'package.json','package-lock.json','scripts/run-repair4-audit.mjs',...(replay?['tests/historical-repair4-replay.mjs']:[]),...tests];
const sha256=Object.fromEntries(files.map(f=>[f,createHash('sha256').update(readFileSync(path.join(root,f))).digest('hex')]));
const report={date:new Date().toISOString(),candidate:'kz-dsh 0.2.5',host:'@deepseek-ai/dsh 0.2.0-rc.2',node:process.version,platform:process.platform,paid_api_calls:0,deployed:false,exit_code:run.status,totals,historical_replay:replay,scope:'Offline units and official DSH ToolRuntime/AgentLoop with scripted model adapters; some tests run local public Node child checks. Not production Linux Bash, real provider, or benchmark performance validation.',sha256};
writeFileSync(path.join(destination,'summary.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({candidate:report.candidate,...totals,exit_code:run.status,report:path.join(destination,'summary.json')}));
if(run.stderr)console.error(run.stderr);
process.exitCode=run.status!==0?(run.status??1):replay?(replay.exit_code??1):0;
