import { spawnSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url));
const output=path.join(root,'audit','2026-10-11-repair1');mkdirSync(output,{recursive:true});
const regression=spawnSync(process.execPath,['--test','--test-reporter=tap',...readdirSync(path.join(root,'tests')).filter(x=>x.endsWith('.test.mjs')).sort().map(x=>'tests/'+x)],{cwd:root,encoding:'utf8',maxBuffer:16*1024*1024});
writeFileSync(path.join(output,'regression-tests.tap'),regression.stdout??'');
const regressionCases=[...(regression.stdout??'').matchAll(/^(not ok|ok) \d+ - (.+)$/gm)].map(m=>({name:m[2],passed:m[1]==='ok'}));
writeFileSync(path.join(output,'regression-results.json'),JSON.stringify({exit_code:regression.status,total:regressionCases.length,passed:regressionCases.filter(x=>x.passed).length,failed:regressionCases.filter(x=>!x.passed).length,cases:regressionCases},null,2));
const run=spawnSync(process.execPath,['--test','--test-reporter=tap','tests/deep-audit.mjs'],{cwd:root,encoding:'utf8',maxBuffer:16*1024*1024});
writeFileSync(path.join(output,'contract-tests.tap'),run.stdout??'');writeFileSync(path.join(output,'contract-tests.stderr.txt'),run.stderr??'');
const cases=[...(run.stdout??'').matchAll(/^(not ok|ok) \d+ - (.+)$/gm)].map(m=>({name:m[2],passed:m[1]==='ok'}));
const report={date:new Date().toISOString(),node:process.version,scope:'offline migration-contract audit; no API',paid_api_requests:0,exit_code:run.status,signal:run.signal,error:run.error?.message,cases,
  total:cases.length,passed:cases.filter(c=>c.passed).length,failed:cases.filter(c=>!c.passed).length,
  candidate_sha256:Object.fromEntries([...readdirSync(path.join(root,'src')).filter(x=>x.endsWith('.mjs')).map(x=>'src/'+x),'config/kz.patch.yml','package-lock.json'].map(p=>[p,createHash('sha256').update(readFileSync(path.join(root,p))).digest('hex')]))};
writeFileSync(path.join(output,'contract-results.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({regression:{total:regressionCases.length,passed:regressionCases.filter(x=>x.passed).length,exit_code:regression.status},total:report.total,passed:report.passed,failed:report.failed,exit_code:run.status,report:path.join(output,'contract-results.json'),cases},null,2));
process.exitCode=regression.status===0&&run.status===0?0:1;
