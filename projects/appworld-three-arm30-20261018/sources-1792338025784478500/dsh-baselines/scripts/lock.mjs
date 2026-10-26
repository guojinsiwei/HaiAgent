import {readFile,readdir,writeFile,mkdir} from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),projects=path.dirname(root),workspace=path.dirname(projects);
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
async function tree(dir,prefix='',out={}){
  for(const e of (await readdir(dir,{withFileTypes:true})).sort((a,b)=>a.name.localeCompare(b.name))){
    if(['node_modules','.runtime','audit','__pycache__'].includes(e.name)||e.name==='source-lock.json')continue;
    const rel=prefix+e.name,full=path.join(dir,e.name);
    if(e.isDirectory())await tree(full,rel+'/',out);else if(e.isFile())out[rel]=sha(await readFile(full));
  }return out;
}
const files={};
for(const project of ['dsh-baselines','recuris-dsh','taco-dsh'])await tree(path.join(projects,project),project+'/',files);
const upstreamRoot=path.join(projects,'recuris-dsh/vendor/upstream');
const upstream=JSON.parse(await readFile(path.join(upstreamRoot,'manifest.json'),'utf8'));
const upstreamVerified=[];
for(const f of upstream.files){const actual=sha(await readFile(path.join(upstreamRoot,f.path)));if(actual!==f.sha256)throw new Error('Recuris upstream snapshot changed: '+f.path);upstreamVerified.push(f.path);}
const recurisHistory={};
for(const f of ['working.py','memory.py','protocol.py','prompts.py','response_text.py']){
  const historical=path.join(workspace,'experiment_records/longcli-recuris-frozen-small20-20261007/recuris/src/recuris',f);
  const hash=sha(await readFile(historical));
  if(sha(await readFile(path.join(projects,'recuris-dsh/vendor/recuris',f)))!==hash)throw new Error('Recuris historical module drift: '+f);
  recurisHistory[f]=hash;
}
const history=JSON.parse(await readFile(path.join(workspace,'experiment_records/longcli-lats-taco-small20-20261007/source-provenance.json'),'utf8'));
const tacoVerified=[];
for(const [f,expected] of Object.entries(history.vendor_hashes)){
  const source=path.join(workspace,'experiment_records/longcli-lats-taco-small20-20261007',f);
  if(sha(await readFile(source))!==expected)throw new Error('TACO historical seal changed: '+f);
  const copied=path.join(projects,'taco-dsh/vendor',f);
  if(!f.endsWith('__init__.py')&&sha(await readFile(copied))!==expected)throw new Error('TACO vendored mechanism changed: '+f);
  tacoVerified.push(f);
}
const dsh={};
for(const pkg of ['dsh','dsh-agent-loop','dsh-session','dsh-session-projection','dsh-tools','dsh-system-prompt','dsh-llm','dsh-llm-deepseek','dsh-llm-retry','dsh-compaction-basic','dsh-token-meter','dsh-tool-bash','dsh-bash-local','dsh-subprocess-local']){
  const dir=path.join(root,'node_modules/@deepseek-ai',pkg),p=JSON.parse(await readFile(path.join(dir,'package.json'),'utf8'));
  if(p.version!=='0.2.0-rc.2')throw new Error('DSH version mismatch '+pkg);
  dsh[pkg]={version:p.version,files:await tree(path.join(dir,'lib'))};
}
const common=JSON.parse(await readFile(path.join(root,'config/common.json'),'utf8'));
const lock={schema:1,created:new Date().toISOString(),recuris:{repository:upstream.repository,commit:upstream.commit,verifiedFiles:upstreamVerified,
  actualRun:'longcli-recuris-large20-20261009; protocol repair follow-up longcli-recuris-protocol-repair4-20261009',historicalModuleHashes:recurisHistory,variant:'frozen; no Meta/TTA'},
  taco:{repository:'https://github.com/multimodal-art-projection/TACO',commit:history.repositories.taco,verifiedFiles:tacoVerified,
    variant:'task-local evolution; no cross-task cache',vendorChange:'compression/__init__.py does not import POSIX global cache'},
  dsh:{version:'0.2.0-rc.2',npmIntegrity:'sha512-EAJ3gPNcVt/uv8X19PMm9NkVhWgT7xXNMk0UKCVm+IQ5rpSQOcsMUa0HWlnYYVybKMsccjcRB21vVVsaXQ6IdA==',
    gitHead:null,note:'Official npm metadata does not publish gitHead. Pin published compiled source hashes; historical local git tree 5badb150 is 0.2.1-alpha.1 and is NOT this runtime.',packages:dsh},
  commonConfigSha256:sha(JSON.stringify(common)),sourceFiles:files,sourceTreeSha256:sha(JSON.stringify(files))};
await writeFile(path.join(root,'source-lock.json'),JSON.stringify(lock,null,2));
console.log(JSON.stringify({sourceTreeSha256:lock.sourceTreeSha256,commonConfigSha256:lock.commonConfigSha256,sourceFiles:Object.keys(files).length,dshPackages:Object.keys(dsh).length}));
