import {spawnSync} from 'node:child_process';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import path from 'node:path';
const root=path.resolve(process.argv[2]);
const manifests=JSON.parse(readFileSync(path.join(root,'comparison.json'),'utf8'));
for(const m of manifests){
  mkdirSync(m.home,{recursive:true});
  const env=Object.fromEntries(['PATH','SystemRoot','WINDIR','TEMP','TMP'].filter(k=>process.env[k]).map(k=>[k,process.env[k]]));
  env.DSH_HOME=m.home;
  const args=m.argv.slice(1);args.pop();args.push('--dump-config');
  const p=spawnSync(process.execPath,args,{cwd:m.workspace,env,encoding:'utf8',windowsHide:true});
  writeFileSync(path.join(root,m.algorithm,'dump.yml'),p.stdout??'');
  writeFileSync(path.join(root,m.algorithm,'dump.stderr.txt'),p.stderr??'');
  if(p.status!==0)throw new Error(`${m.algorithm} official config dump failed: ${p.stderr}`);
  console.log(`${m.algorithm}: official CLI config resolved, no run`);
}
