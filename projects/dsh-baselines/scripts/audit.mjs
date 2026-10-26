import {spawnSync} from 'node:child_process';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url));
const python=process.env.BASELINE_PYTHON??'C:/Users/54177/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe';
const dir=path.join(root,'audit',new Date().toISOString().replace(/[:.]/g,'-'));mkdirSync(dir,{recursive:true});
const runs=[['dsh-lifecycle',process.execPath,['--test','--test-reporter=tap','tests/lifecycle.test.mjs','tests/edge.test.mjs','tests/official-wire.test.mjs']],
  ['algorithm-units',python,['tests/algorithms.py']]];
const results=[];
for(const [name,command,args] of runs){
  const p=spawnSync(command,args,{cwd:root,encoding:'utf8',windowsHide:true,env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
  writeFileSync(path.join(dir,name+'.stdout.txt'),p.stdout??'');writeFileSync(path.join(dir,name+'.stderr.txt'),p.stderr??'');
  results.push({name,exitCode:p.status,signal:p.signal});console.log(`${name}: ${p.status===0?'PASS':'FAIL'}`);
}
const result={created:new Date().toISOString(),platform:process.platform,node:process.version,python,runs:results,
  passed:results.every(r=>r.exitCode===0),realModelApiCalls:0,mockHttpRequests:'counted and asserted against local server',
  scope:'Official DSH lifecycle, native real bash/subprocess, real compaction; scripted model and separate official adapter SSE test',
  linuxDshLifecycle:false,algorithmEfficacyClaim:false};
writeFileSync(path.join(dir,'results.json'),JSON.stringify(result,null,2));
writeFileSync(path.join(root,'audit/latest.json'),JSON.stringify({directory:dir,...result},null,2));
if(!result.passed)process.exitCode=1;
