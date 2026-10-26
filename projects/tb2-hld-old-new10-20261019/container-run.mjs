import fs from 'node:fs';
import {spawn} from 'node:child_process';
import {deadline} from './deadline.mjs';
const bundle=JSON.parse(fs.readFileSync(0,'utf8'));
if(bundle.spending?.CAMPAIGN_BUDGET_REQUIRED!=='1'||!['hld-old','hld-new'].includes(bundle.arm))throw Error('Invalid campaign');
const logs='/logs/agent/live';fs.mkdirSync(logs,{recursive:true});
const cwd=process.cwd();if(cwd==='/')throw Error('Explicit task workspace required');
fs.writeFileSync(cwd+'/BENCHMARK_INSTRUCTION.md',bundle.instruction,{flag:'wx'});
const env={...process.env};
for(const k of ['KZ_APPWORLD','DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL'])delete env[k];
Object.assign(env,{TAOTOKEN_API_KEY:bundle.key,DSH_HOME:logs+'/dsh-home',KZ_WORKSPACE:cwd,KZ_AUDIT_DIR:logs+'/kz',KZ_TASK_INSTRUCTION_PATH:'BENCHMARK_INSTRUCTION.md',HLD_PLANNER_PROTOCOL:bundle.arm==='hld-new'?'3':'2',
 KZ_TRANSPORT_AUDIT_PATH:logs+'/transport.jsonl',PAIRED_AUDIT_DIR:logs,PAIRED_ARM:'kz',EXPERIMENT_ARM:bundle.arm,
 DSH_PERMISSION_MODE:'danger-full-access',DSH_APPROVAL_POLICY:'never',DSH_TELEMETRY_DISABLED:'1',HTTPS_PROXY:bundle.proxy,HTTP_PROXY:bundle.proxy,NO_PROXY:bundle.no_proxy+',10.123.0.1',PATH:'/opt/node/bin:'+env.PATH,DSH_ROUTE_AUDIT:logs+'/route.jsonl',DSH_EXPECT_ENDPOINT:'https://api.taotoken.net/token/v1/messages',...bundle.spending});
const args=['--use-env-proxy','--import','/opt/kz/provider-guard.mjs','--import','/opt/kz/route-audit.mjs','--import','/opt/kz/boot-guard.mjs','/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js','--profile','headless'];
for(const patch of ['config/common.patch.yml','route.patch.yml','.runtime/transport.patch.yml',...(bundle.arm==='hld-old'?['.runtime/hld-old.patch.yml']:['.runtime/kz.patch.yml','.runtime/hld-new-context.patch.yml'])])args.push('--patch','/opt/kz/'+patch);
args.push('--json','-');
const out=fs.openSync(logs+'/dsh.jsonl','wx'),err=fs.openSync(logs+'/dsh.stderr.log','wx');
const child=spawn('/opt/node/bin/node',args,{cwd,env,stdio:['pipe',out,err],detached:true});bundle.key='';delete env.TAOTOKEN_API_KEY;
child.stdin.end(bundle.instruction);child.stdin.on('error',()=>{});
const guard=deadline(child,7200,r=>fs.writeFileSync(logs+'/wall-limit.json',JSON.stringify({...r,attempt_id:bundle.attempt_id})));
const timer=setInterval(()=>{for(const n of ['limit-stop.json','budget-stop.json','provider-stop.json'])if(fs.existsSync(logs+'/'+n))guard.terminate(n);},250);
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{try{process.kill(-child.pid,signal);}catch{}});
const result=await new Promise(resolve=>{child.on('error',()=>resolve({exit_code:127,signal:null}));child.on('exit',(c,s)=>resolve({exit_code:c??(s==='SIGKILL'?137:143),signal:s}));});
guard.finish();clearInterval(timer);fs.closeSync(out);fs.closeSync(err);
fs.writeFileSync(logs+'/agent-exit.json',JSON.stringify({...result,attempt_id:bundle.attempt_id,timed_out:guard.reason==='solver_wall_limit',stopped_by:guard.reason,arm:bundle.arm}));process.exitCode=result.exit_code;
