// One isolated task. Key exists only on stdin and in the DSH child environment.
import fs from 'node:fs';
import {deadline} from './deadline.mjs';
import {spawn} from 'node:child_process';
const bundle=JSON.parse(fs.readFileSync(0,'utf8'));
if(!['kz','dsh'].includes(bundle.arm))throw Error('Unknown arm');
const logs='/logs/agent/live';fs.mkdirSync(logs,{recursive:true});
const cwd=process.cwd();if(cwd==='/')throw Error('Explicit non-root task workdir required');
const taskPath=cwd+'/BENCHMARK_INSTRUCTION.md';
fs.writeFileSync(taskPath,bundle.instruction,{flag:'wx'});
const env={...process.env};
for(const key of ['DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL'])delete env[key];
Object.assign(env,{TAOTOKEN_API_KEY:bundle.key,DSH_HOME:logs+'/dsh-home',KZ_WORKSPACE:cwd,KZ_AUDIT_DIR:logs+'/kz',
  KZ_TASK_INSTRUCTION_PATH:'BENCHMARK_INSTRUCTION.md',KZ_TRANSPORT_AUDIT_PATH:logs+'/transport.jsonl',PAIRED_AUDIT_DIR:logs,
  PAIRED_ARM:bundle.arm,
  DSH_PERMISSION_MODE:'danger-full-access',DSH_APPROVAL_POLICY:'never',DSH_TELEMETRY_DISABLED:'1',
  HTTPS_PROXY:bundle.proxy,HTTP_PROXY:bundle.proxy,NO_PROXY:bundle.no_proxy,
  PATH:'/opt/node/bin:'+env.PATH,DSH_ROUTE_AUDIT:logs+'/route.jsonl',
  DSH_EXPECT_ENDPOINT:'https://api.taotoken.net/token/v1/messages'});
const args=['--use-env-proxy','--import','/opt/kz/route-audit.mjs','--import','/opt/kz/boot-guard.mjs','/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js','--profile','headless'];
for(const patch of ['config/common.patch.yml','route.patch.yml','.runtime/transport.patch.yml',...(bundle.arm==='kz'?['.runtime/kz.patch.yml']:[])])args.push('--patch','/opt/kz/'+patch);
args.push('--json','-');
const out=fs.openSync(logs+'/dsh.jsonl','wx'),err=fs.openSync(logs+'/dsh.stderr.log','wx');
const child=spawn('/opt/node/bin/node',args,{cwd,env,stdio:['pipe',out,err],detached:true});
bundle.key='';delete env.TAOTOKEN_API_KEY;
child.stdin.end(bundle.instruction);
const guard=deadline(child,10800,r=>fs.writeFileSync(logs+'/wall-limit.json',JSON.stringify(r)));
// Same three-hour solver budget as native KZ; no protocol-error early stop.
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{try{process.kill(-child.pid,signal);}catch{}});
child.stdin.on('error',()=>{});
const result=await new Promise(resolve=>{child.on('error',()=>resolve({exit_code:127,signal:null}));child.on('exit',(c,s)=>resolve({exit_code:c??(s==='SIGKILL'?137:s==='SIGTERM'?143:1),signal:s}));});
guard.finish();fs.closeSync(out);fs.closeSync(err);
fs.writeFileSync(logs+'/agent-exit.json',JSON.stringify({...result,timed_out:guard.expired,arm:bundle.arm,budget_mode:'unlimited'}));
console.log(JSON.stringify(result));
process.exitCode=result.exit_code;
