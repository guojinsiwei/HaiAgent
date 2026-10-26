import fs from 'node:fs';
import {spawn} from 'node:child_process';
import {deadline} from '/opt/kz/deadline.mjs';
const bundle=JSON.parse(fs.readFileSync(0,'utf8'));
if(bundle.spending?.CAMPAIGN_BUDGET_REQUIRED!=='1'||!['hld','kzdsh-new','recuris','dsh'].includes(bundle.arm))throw Error('Invalid campaign');
const env={...process.env};
Object.assign(env,{KZ_APPWORLD:'1',HLD_PLANNER_PROTOCOL:'3',TAOTOKEN_API_KEY:bundle.key,DSH_HOME:'/audit/dsh-home',KZ_WORKSPACE:'/app',KZ_AUDIT_DIR:'/audit/kz',KZ_TASK_INSTRUCTION_PATH:'INSTRUCTION.md',
KZ_TRANSPORT_AUDIT_PATH:'/audit/transport.jsonl',PAIRED_AUDIT_DIR:'/audit',PAIRED_ARM:bundle.arm==='dsh'?'dsh':'kz',EXPERIMENT_ARM:bundle.arm,
DSH_PERMISSION_MODE:'danger-full-access',DSH_APPROVAL_POLICY:'never',DSH_TELEMETRY_DISABLED:'1',HTTPS_PROXY:bundle.proxy,HTTP_PROXY:bundle.proxy,
NO_PROXY:bundle.no_proxy+',world',DSH_ROUTE_AUDIT:'/audit/route.jsonl',DSH_EXPECT_ENDPOINT:'https://api.taotoken.net/token/v1/messages',...bundle.spending});
const args=['--use-env-proxy','--import','/opt/kz/provider-guard.mjs','--import','/opt/kz/route-audit.mjs','--import','/opt/kz/boot-guard.mjs','/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js','--profile','headless'];
const patches=['/opt/kz/config/common.patch.yml','/opt/kz/route.patch.yml','/opt/kz/.runtime/transport.patch.yml'];
if(['hld','kzdsh-new'].includes(bundle.arm))patches.push('/opt/kz/.runtime/kz.patch.yml','/opt/kz/.runtime/hld-new-context.patch.yml');
if(bundle.arm==='recuris'){
  const c={algorithm:'recuris',instruction:bundle.instruction,workspace:'/app',auditDir:'/audit/recuris',python:'/opt/recuris/bin/python',
    route:{provider:'deepseek-official',model:'deepseek-flash',temperature:0,maxTokens:16384},budget:{apiRequests:400,tools:600,wallSeconds:7200},offline:false,crossTaskMemory:false};
  fs.writeFileSync('/audit/recuris.patch.yml',JSON.stringify([{insert:[{id:'baseline-algorithm',name:'/opt/recuris-dsh/src/plugin.mjs',config:c}]}]));
  patches.push('/audit/recuris.patch.yml');
}
for(const patch of patches)args.push('--patch',patch);args.push('--json','-');
const out=fs.openSync('/audit/dsh.jsonl','wx'),err=fs.openSync('/audit/dsh.stderr.log','wx');
const child=spawn('/opt/node/bin/node',args,{cwd:'/app',env,stdio:['pipe',out,err],detached:true});
bundle.key='';delete env.TAOTOKEN_API_KEY;child.stdin.end(bundle.instruction);child.stdin.on('error',()=>{});
const guard=deadline(child,7200,r=>fs.writeFileSync('/audit/wall-limit.json',JSON.stringify(r)));
const timer=setInterval(()=>{for(const name of ['limit-stop.json','budget-stop.json','provider-stop.json'])if(fs.existsSync('/audit/'+name))guard.terminate(name);},250);
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{try{process.kill(-child.pid,signal);}catch{}});
const result=await new Promise(resolve=>{child.on('error',()=>resolve({exit_code:127}));child.on('exit',(c,s)=>resolve({exit_code:c??(s==='SIGKILL'?137:143),signal:s}));});
guard.finish();clearInterval(timer);fs.closeSync(out);fs.closeSync(err);
fs.writeFileSync('/audit/agent-exit.json',JSON.stringify({...result,stopped_by:guard.reason,arm:bundle.arm}));
process.exitCode=result.exit_code;
