import {readFile,writeFile,readdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=fileURLToPath(new URL('./',import.meta.url));
const source=path.resolve(root,'../tb2-hld-mechanism-ab10-20261022/candidate');
const hash=b=>createHash('sha256').update(b).digest('hex');
async function files(dir,relative='') {
  const out={};
  for(const row of await readdir(path.join(dir,relative),{withFileTypes:true})) {
    if(row.isSymbolicLink()||row.name==='__pycache__')continue;
    const p=path.posix.join(relative,row.name);
    if(row.isDirectory())Object.assign(out,await files(dir,p));
    else out[p]=hash(await readFile(path.join(dir,p)));
  }
  return out;
}
async function manifest(dir) {
  const out={};
  for(const part of ['src','config','scripts','tests'])Object.assign(out,await files(dir,part));
  out['package.json']=hash(await readFile(path.join(dir,'package.json')));return out;
}
const original=await manifest(source),baseline=await manifest(path.join(root,'offline-baseline')),candidate=await manifest(path.join(root,'candidate'));
const differences=(a,b)=>[...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>a[k]!==b[k]);
function tap(text) {
  const count=k=>Number(text.match(new RegExp('^# '+k+' (\\d+)','m'))?.[1]??NaN);
  return {tests:count('tests'),pass:count('pass'),fail:count('fail'),skipped:count('skipped'),cancelled:count('cancelled'),
    failures:text.split(/\r?\n/).filter(x=>/^not ok \d+ - /.test(x)).map(x=>x.replace(/^not ok \d+ - /,''))};
}
const b=tap(await readFile(path.join(root,'validation/baseline.tap'),'utf8'));
const c=tap(await readFile(path.join(root,'validation/candidate-final.tap'),'utf8'));
const result={createdAt:new Date().toISOString(),status:'offline_candidate_not_deployed',modelCalls:0,source,
  originalDifferencesFromFrozenCopy:differences(original,baseline),changedFiles:differences(baseline,candidate),
  tests:{baseline:b,candidate:c,newFailures:c.failures.filter(x=>!b.failures.includes(x)),resolvedFailures:b.failures.filter(x=>!c.failures.includes(x))},
  candidateManifest:candidate,baselineManifest:baseline,
  deploymentGate:'No deployment or paid comparison was started. Paired comparison and review are required before promotion.'};
await writeFile(path.join(root,'validation/audit.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({originalChanges:result.originalDifferencesFromFrozenCopy,changed:result.changedFiles,baseline:b,candidate:c,newFailures:result.tests.newFailures},null,2));
if(result.originalDifferencesFromFrozenCopy.length||result.tests.newFailures.length||!Number.isFinite(c.tests)||c.cancelled)process.exitCode=1;
