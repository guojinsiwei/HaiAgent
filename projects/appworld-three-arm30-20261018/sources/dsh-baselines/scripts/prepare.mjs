// Prepare only. It never starts DSH, Docker, a network client, or a model call.
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import yaml from 'js-yaml';
const args=Object.fromEntries(process.argv.slice(2).reduce((a,v,i,all)=>i%2?a:[...a,[v.replace(/^--/,''),all[i+1]]],[]));
if(!args.task||!args.out||!args.python)throw new Error('Usage: node scripts/prepare.mjs --task PUBLIC_INSTRUCTION --out NEW_DIRECTORY --python PYTHON [--image sha256:DIGEST]');
const root=fileURLToPath(new URL('../',import.meta.url));
const shared=JSON.parse(await readFile(path.join(root,'config/common.json'),'utf8'));
const environment=JSON.parse(await readFile(path.join(root,'environment-lock.json'),'utf8'));
const imageDigest=args.image??environment.imageId;
if(!/^sha256:[a-f0-9]{64}$/.test(imageDigest))throw new Error('Runtime image must be an immutable sha256 digest');
const instruction=await readFile(path.resolve(args.task),'utf8');
const sha=v=>createHash('sha256').update(v).digest('hex');
const out=path.resolve(args.out);await mkdir(out,{recursive:false});
const commonPatch=[
  {id:'tools',config:{mode:'native'}},
  {id:'agent-loop',config:{agents:[],maxParallelToolCalls:1}},
  {id:'agent-default-model',config:{provider:shared.route.provider,model:shared.route.model}},
  {id:'compaction-basic',config:shared.compaction},
  {id:'llm-deepseek',config:{thinking:'disabled',reasoningEffort:'off',maxTokens:shared.route.maxTokens,defaultContextWindow:shared.contextWindow,models:[{id:shared.route.model,name:shared.route.model,contextWindow:shared.contextWindow,maxTokens:shared.route.maxTokens}]}},
  {id:'tool-bash',disabled:false,config:{enableRunInBackground:false,promoteOnTimeout:false}},
  {id:'bash-sandbox',config:{timeoutMs:shared.commandTimeoutMs,maxTimeoutMs:shared.commandTimeoutMs}},
  ...['tool-todo','tool-goal','tool-subagent','tool-subagent-fork','tool-subagent-control','tool-subagent-list-agents','tool-workflow','tool-web','session-title-llm','llm-deepseek-account','skill-filesystem','session-telemetry-otel'].map(id=>({id,disabled:true})),
];
await writeFile(path.join(out,'common.patch.yml'),yaml.dump(commonPatch));
const manifests=[];
for(const algorithm of ['native','recuris','taco']) {
  const runId=randomUUID(),dir=path.join(out,algorithm);
  await mkdir(dir);const workspace=path.join(dir,'workspace');await mkdir(workspace);
  await writeFile(path.join(workspace,'INSTRUCTION.md'),instruction);
  const config={...shared,taskId:runId,instruction,workspace,auditDir:path.join(dir,'audit'),python:path.resolve(args.python)};
  const plugin=algorithm==='native'?path.join(root,'src/plugin.mjs'):path.join(root,'..',`${algorithm}-dsh/src/plugin.mjs`);
  const patch=[{insert:[{id:'baseline-algorithm',name:plugin,config}]}];
  await writeFile(path.join(dir,'algorithm.patch.yml'),yaml.dump(patch));
  const manifest={algorithm,runId,containerName:`dsh-${algorithm}-${runId}`,sessionId:null,sessionCreatedBy:'DSH fresh session',
    workspace,home:path.join(dir,'home'),audit:config.auditDir,python:config.python,
    commonConfigSha256:sha(JSON.stringify(shared)),commonPatchSha256:sha(yaml.dump(commonPatch)),
    algorithmPatchSha256:sha(yaml.dump(patch)),taskSha256:sha(instruction),imageDigest,
    preparedOnly:true,liveApproved:false,argv:[process.execPath,path.join(root,'node_modules/@deepseek-ai/dsh/lib/bin.js'),'headless',
      '--patch',path.join(out,'common.patch.yml'),'--patch',path.join(dir,'algorithm.patch.yml'),
      instruction],
    isolation:{freshContainer:true,freshWorkspace:true,freshHome:true,freshTmp:true,noLearnedCache:true,
      cpu:shared.environment.cpu,memoryGiB:shared.environment.memoryGiB,pids:shared.environment.pids},
    requiredBeforeLive:['User approval','Verify runtime image against environment-lock.json','Python pydantic==2.13.5',
      'Task starter and runtime image digests','Shared model-only gateway and new explicitly supplied credential','Task-specific native sandbox rehearsal; repeat lifecycle tests if runtime changes']};
  await writeFile(path.join(dir,'manifest.json'),JSON.stringify(manifest,null,2));manifests.push(manifest);
}
if(new Set(manifests.map(m=>m.commonConfigSha256)).size!==1)throw new Error('configuration drift');
await writeFile(path.join(out,'comparison.json'),JSON.stringify(manifests,null,2));
console.log(JSON.stringify({prepared:out,commonConfigSha256:manifests[0].commonConfigSha256,modelCalls:0,launched:false}));
