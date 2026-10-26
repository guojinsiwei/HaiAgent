import {spawnSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),projects=path.dirname(root);
const result=JSON.parse(readFileSync(path.join(root,'audit/linux/results.json'),'utf8').replace(/^\uFEFF/,''));
if(!result.passed)throw new Error('Linux tests must pass before sealing');
const files=['dsh-baselines/src/plugin.mjs','dsh-baselines/src/bridge.mjs','dsh-baselines/src/transport.mjs',
  'dsh-baselines/config/common.json','recuris-dsh/src/plugin.mjs','recuris-dsh/worker.py',
  'recuris-dsh/vendor/recuris/memory.py','recuris-dsh/vendor/recuris/working.py',
  'taco-dsh/src/plugin.mjs','taco-dsh/worker.py','taco-dsh/vendor/taco_native/output_filter.py',
  ...['planner','evolver','feedback','dynamic_filter','models','seed_rules'].map(n=>`taco-dsh/vendor/taco_native/compression/${n}.py`)];
const code=`const fs=require('fs'),crypto=require('crypto');const files=${JSON.stringify(files)};console.log(JSON.stringify({node:process.version,files:Object.fromEntries(files.map(f=>[f,crypto.createHash('sha256').update(fs.readFileSync('/opt/baselines/'+f)).digest('hex')]))}));`;
const p=spawnSync('docker',['run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges',result.imageId,'node','-e',code],{encoding:'utf8',windowsHide:true});
if(p.status!==0)throw new Error(p.stderr);
const snapshot=JSON.parse(p.stdout);
for(const [file,hash] of Object.entries(snapshot.files))if(createHash('sha256').update(readFileSync(path.join(projects,file))).digest('hex')!==hash)throw new Error('Tested image differs from delivered source: '+file);
writeFileSync(path.join(root,'environment-lock.json'),JSON.stringify({imageId:result.imageId,image:result.image,
  inputs:JSON.parse(readFileSync(path.join(root,'audit/linux-inputs.json'),'utf8')),testedSource:snapshot,
  networkDuringTests:'none; per-container localhost only',realModelApiCalls:0},null,2));
console.log('Linux image and 17 delivered mechanism/config files match; environment locked.');
