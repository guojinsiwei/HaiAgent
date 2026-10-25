// Stdin-only, no credentials. Inspect/signal ONLY the pinned solver tree.
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
export const WRAPPER='/opt/kz/container-run.mjs';
export const SOLVER='/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js';
const receiptPath='/logs/agent/live/server-timeout.json';
function stat(pid){
  try{
    const s=fs.readFileSync(`/proc/${pid}/stat`,'utf8'),end=s.lastIndexOf(')'),x=s.slice(end+2).split(' ');
    return{pid:Number(pid),state:x[0],ppid:Number(x[1]),pgrp:Number(x[2]),start:Number(x[19])};
  }catch{return null;}
}
function processes(){return fs.readdirSync('/proc').filter(n=>/^\d+$/.test(n)).map(stat).filter(Boolean);}
function argv(pid){try{return fs.readFileSync(`/proc/${pid}/cmdline`,'utf8').split('\0').filter(Boolean);}catch{return[];}}
export function descendants(table,root){
  const ids=new Set([root]);let changed=true;
  while(changed){changed=false;for(const p of table)if(ids.has(p.ppid)&&!ids.has(p.pid)){ids.add(p.pid);changed=true;}}
  return table.filter(p=>ids.has(p.pid));
}
export function sameIdentity(a,b){return !!a&&!!b&&a.pid===b.pid&&a.start===b.start&&a.pid>1;}
function live(p){return p&&!['Z','X'].includes(p.state);}
function signal(p,s){
  const now=stat(p.pid);if(!sameIdentity(p,now)||!live(now))return false;
  try{process.kill(p.pid,s);return true;}catch(e){if(e.code!=='ESRCH')throw e;return false;}
}
function readReceipt(){try{return JSON.parse(fs.readFileSync(receiptPath,'utf8'));}catch{return null;}}
function writeReceipt(r){fs.writeFileSync(receiptPath+'.tmp',JSON.stringify(r),{mode:0o644});fs.renameSync(receiptPath+'.tmp',receiptPath);}
function locate(){
  const table=processes();
  // Read only candidate node argument vectors; never environ or general tool argv.
  const wrappers=table.filter(p=>{try{return fs.readlinkSync(`/proc/${p.pid}/exe`).split('/').pop()==='node'&&argv(p.pid).includes(WRAPPER);}catch{return false;}});
  if(wrappers.length!==1)return{table,error:'solver_wrapper_not_unique',wrapper_count:wrappers.length};
  const wrapper=wrappers[0],solvers=table.filter(p=>p.ppid===wrapper.pid&&argv(p.pid).includes(SOLVER));
  if(solvers.length!==1)return{table,wrapper,error:'solver_child_not_unique',solver_count:solvers.length};
  const solver=solvers[0];
  const ticks=Number(execFileSync('getconf',['CLK_TCK'],{encoding:'utf8',timeout:3000}).trim());
  if(!Number.isFinite(ticks)||ticks<=0)throw Error('Unknown process clock scale');
  const uptime=Number(fs.readFileSync('/proc/uptime','utf8').split(' ')[0]);
  return{table,wrapper,solver,elapsed_seconds:Math.max(0,uptime-solver.start/ticks)};
}
function main(request){
  if(request.mode==='enforce'&&(request.limit_seconds!==10800||request.grace_seconds!==15))throw Error('Invalid watchdog policy');
  const receipt=readReceipt();
  if(receipt&&request.mode==='enforce'){
    if(receipt.job!==request.job||receipt.trial!==request.trial)throw Error('Timeout receipt identity mismatch');
    if(receipt.state==='stopped')return receipt;
    if(!sameIdentity(stat(receipt.wrapper.pid),receipt.wrapper)||!argv(receipt.wrapper.pid).includes(WRAPPER))throw Error('Wrapper identity changed; refusing stored signals');
    // Recover a partially completed stop after watchdog/exec failure. The wrapper
    // was frozen, so Harbor cannot begin artifact grading before child cleanup.
    const age=Date.now()-receipt.term_at_ms;
    if(age<request.grace_seconds*1000)return receipt;
    const table=processes(),root=stat(receipt.solver.pid);
    const targets=[...receipt.descendants];
    if(sameIdentity(root,receipt.solver))targets.push(...descendants(table,root.pid));
    for(const p of targets)signal(p,'SIGKILL');
    signal(receipt.wrapper,'SIGCONT');
    receipt.state='stopped';receipt.finished_at=new Date().toISOString();writeReceipt(receipt);return receipt;
  }
  const found=locate();
  if(found.error)return{state:'not_solving',reason:found.error,receipt};
  const view={state:'solving',solver:found.solver,wrapper:found.wrapper,elapsed_seconds:found.elapsed_seconds,receipt};
  if(request.mode==='probe')return view;
  if(request.mode!=='enforce')throw Error('Invalid watchdog mode');
  if(request.solver&&!sameIdentity(request.solver,found.solver))throw Error('Solver changed since host probe');
  if(found.elapsed_seconds<request.limit_seconds)return view;
  const saved={state:'terminating',reason:'server_wall_limit_3h',job:request.job,trial:request.trial,
    limit_seconds:request.limit_seconds,elapsed_seconds:found.elapsed_seconds,term_at_ms:Date.now(),
    solver:found.solver,wrapper:found.wrapper,descendants:descendants(found.table,found.solver.pid)};
  writeReceipt(saved);
  // Pause wrapper receipt collection, not the task container or service PID 1.
  signal(found.wrapper,'SIGSTOP');
  for(const p of [...saved.descendants].reverse())signal(p,'SIGTERM');
  return saved;
}
if(process.argv[1]==='-'||process.argv[1]?.endsWith('container_guard.mjs')){
  try{const input=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(main(input)));}
  catch(error){console.log(JSON.stringify({state:'guard_error',error:error.message}));process.exitCode=1;}
}
