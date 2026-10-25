// This wrapper contains no algorithm. It keeps credentials off argv and disk.
import fs from 'node:fs';
import {spawn} from 'node:child_process';
const b=JSON.parse(fs.readFileSync(0,'utf8')),logs='/logs/agent/live';fs.mkdirSync(logs,{recursive:true});
const env={...process.env,HTTPS_PROXY:b.proxy,HTTP_PROXY:b.proxy,NO_PROXY:b.no_proxy,PYTHONUNBUFFERED:'1'};
for(const k of ['TAOTOKEN_API_KEY','DEEPSEEK_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY'])delete env[k];
const child=spawn('python3',['/opt/kz-standalone/solve.py'],{env,cwd:process.cwd(),detached:true,stdio:['pipe',fs.openSync(logs+'/solver.stdout.log','wx'),fs.openSync(logs+'/solver.stderr.log','wx')]});
child.stdin.on('error',()=>{});child.stdin.end(JSON.stringify(b));b.key='';
// The server watchdog terminates the entire solver descendant tree after 3h.
// Do not race its child cleanup by terminating only the Python group here.
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{try{process.kill(-child.pid,signal)}catch{}});
const result=await new Promise(resolve=>{child.on('error',()=>resolve({exit_code:127,signal:null}));child.on('exit',(c,s)=>resolve({exit_code:c??(s==='SIGKILL'?137:143),signal:s}));});
fs.writeFileSync(logs+'/agent-exit.json',JSON.stringify({...result,arm:'legacy-kz'}));process.exitCode=result.exit_code;
