// Explicit allowlist. Never package runtime caches, homes, credentials or sessions.
import {readdirSync,readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
const destination=fileURLToPath(new URL('.',import.meta.url));
const root=fileURLToPath(new URL('../../projects/kz-dsh/',import.meta.url));
const files=['package.json','package-lock.json','README.txt',...['src','config','scripts','tests'].flatMap(dir=>readdirSync(path.join(root,dir),{withFileTypes:true}).filter(e=>e.isFile()&&/\.(mjs|yml)$/.test(e.name)).map(e=>dir+'/'+e.name))];
const filesHashes=Object.fromEntries(files.map(name=>[name,createHash('sha256').update(readFileSync(path.join(root,name))).digest('hex')]));
const accepted=JSON.parse(readFileSync(path.join(root,'audit/2026-10-13-repair5/summary.json')));
const deviations=[];
for(const [name,hash] of Object.entries(accepted.sha256))if(filesHashes[name]!==hash) {
  if(!['tests/subgoal-integration-repair5.test.mjs','config/longcli-task.patch.yml','scripts/prepare-config.mjs','README.txt'].includes(name))throw Error('Source differs from offline acceptance: '+name);
  deviations.push({file:name,previous:hash,current:filesHashes[name]??null,reason:'Deployment-only: Linux Python fixture + full LongCLI config materialization; algorithm src unchanged. Server must rerun all regressions before launch.'});
}
execFileSync('tar',['-czf',path.join(destination,'candidate.tar.gz'),...files],{cwd:root});
writeFileSync(path.join(destination,'source-manifest.json'),JSON.stringify({version:'0.2.6',files:filesHashes,accepted_tests:accepted.totals,fixture_deviations:deviations,paid_calls:0},null,2)+'\n');
const scripts=['prepare.py','accept.py','runner.py','status.py','container_run.py','offline.py','settings.mjs','kz-boot-guard.mjs','source-manifest.json'];
execFileSync('tar',['-czf',path.join(destination,'deployment.tar.gz'),...scripts],{cwd:destination});
console.log(JSON.stringify({source_files:files.length,source_sha256:createHash('sha256').update(readFileSync(path.join(destination,'candidate.tar.gz'))).digest('hex'),deployment_files:scripts}));
