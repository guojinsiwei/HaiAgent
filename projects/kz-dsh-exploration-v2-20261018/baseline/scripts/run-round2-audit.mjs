import {spawnSync} from 'node:child_process';
import {mkdirSync,writeFileSync,readFileSync,readdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url));
const label=process.argv[2]??'2026-10-11-round2';
if(!/^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$/.test(label))throw new Error('explicit dated audit directory required');
const output=path.join(root,'audit',label);mkdirSync(output,{recursive:true});
const suites={regression:readdirSync(path.join(root,'tests')).filter(x=>x.endsWith('.test.mjs')).sort().map(x=>'tests/'+x),previous_contracts:['tests/deep-audit.mjs'],new_contracts:['tests/migration-round2.mjs']};
if(process.argv.includes('--round3'))suites.round3_contracts=['tests/migration-round3.mjs'];
const report={date:new Date().toISOString(),node:process.version,paid_api_requests:0,suites:{},source_sha256:Object.fromEntries(readdirSync(path.join(root,'src')).filter(x=>x.endsWith('.mjs')).map(x=>[x,createHash('sha256').update(readFileSync(path.join(root,'src',x))).digest('hex')]))};
for(const [name,files] of Object.entries(suites)) {
  const r=spawnSync(process.execPath,['--test','--test-reporter=tap',...files],{cwd:root,encoding:'utf8',maxBuffer:16*1024*1024});
  writeFileSync(path.join(output,name+'.tap'),r.stdout??'');writeFileSync(path.join(output,name+'.stderr.txt'),r.stderr??'');
  const cases=[...(r.stdout??'').matchAll(/^(not ok|ok) \d+ - (.+)$/gm)].map(m=>({name:m[2],passed:m[1]==='ok'}));
  report.suites[name]={exit_code:r.status,error:r.error?.message,total:cases.length,passed:cases.filter(x=>x.passed).length,failed:cases.filter(x=>!x.passed).length,cases};
  console.log(JSON.stringify({suite:name,...report.suites[name]}));
}
writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));
process.exitCode=Object.values(report.suites).every(x=>x.exit_code===0)?0:1;
