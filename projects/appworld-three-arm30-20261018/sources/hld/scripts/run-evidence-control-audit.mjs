// Offline only: scripted LLM adapters, official local DSH, temporary task files.
// No credentials, provider requests, deployment or existing campaign writes.
import {spawnSync} from 'node:child_process';
import {mkdir,readdir,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url));
const run=path.join(root,'audit','2026-10-14-evidence-control','run-'+new Date().toISOString().replaceAll(/[:.]/g,'-'));
await mkdir(run,{recursive:true});
async function hashes(){
  const result={};
  for(const folder of ['src','tests','config','scripts'])for(const file of (await readdir(path.join(root,folder))).sort()) {
    if(!/\.(mjs|yml|json)$/u.test(file))continue;
    const name=folder+'/'+file;result[name]=createHash('sha256').update(await readFile(path.join(root,name))).digest('hex');
  }
  for(const name of ['package.json','package-lock.json','README.txt'])result[name]=createHash('sha256').update(await readFile(path.join(root,name))).digest('hex');
  return result;
}
const before=await hashes(),tests=(await readdir(path.join(root,'tests'))).filter(f=>f.endsWith('.test.mjs')).sort().map(f=>'tests/'+f);
const result=spawnSync(process.execPath,['--test','--test-reporter=tap',...tests],{cwd:root,encoding:'utf8',maxBuffer:32*1024*1024,windowsHide:true});
const output=(result.stdout??'')+'\n'+(result.stderr??'');await writeFile(path.join(run,'tests.tap'),output);
const host=spawnSync(process.execPath,['scripts/check-host.mjs'],{cwd:root,encoding:'utf8',windowsHide:true});
await writeFile(path.join(run,'host.txt'),(host.stdout??'')+(host.stderr??''));
const after=await hashes(),changed=Object.keys(before).filter(name=>before[name]!==after[name]);
const metric=name=>Number(output.match(new RegExp('^# '+name+' (\\d+)$','m'))?.[1]??NaN);
const summary={version:JSON.parse(await readFile(path.join(root,'package.json'),'utf8')).version,behavior_revision:'evidence-control-1',
  created_at:new Date().toISOString(),node:process.version,platform:process.platform,offline_only:true,provider_calls:0,remote_mutations:0,
  tests:metric('tests'),passed:metric('pass'),failed:metric('fail'),skipped:metric('skipped'),cancelled:metric('cancelled'),
  exit_code:result.status,runner_error:result.error?.message??null,host_check_exit:host.status,changed_during_run:changed,
  source_sha256:before,passed_acceptance:result.status===0&&host.status===0&&changed.length===0&&metric('fail')===0&&metric('cancelled')===0};
await writeFile(path.join(run,'summary.json'),JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify({...summary,source_sha256:undefined,run},null,2));process.exitCode=summary.passed_acceptance?0:1;
