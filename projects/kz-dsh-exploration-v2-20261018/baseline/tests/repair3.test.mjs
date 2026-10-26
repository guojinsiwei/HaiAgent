import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,readFile,readdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import LlmRuntime from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import LocalJobs from '@deepseek-ai/dsh-jobs-local';
import {Session} from '@deepseek-ai/dsh-session';
import {createScope} from '@deepseek-ai/dsh-scope';
import * as plugin from '../src/plugin.mjs';
import {BackgroundJobs} from '../src/background-jobs.mjs';
import {FullTask} from '../src/full-task.mjs';
import {Policy} from '../src/policy.mjs';

const S='sha256:a',deps={'main.py':'file:a'},args={command:'python main.py'};
const call={name:'bash',arguments:args,callId:'c1',commandDependencies:deps};
const snapshot={before:S,after:S,depsBefore:deps,depsAfter:deps,commandDependencies:deps};
const stream=(text='assertion failed',channel='stderr')=>({chunks:[{at:0,text,channel}],next:text.length,lossy:false});
function start(kind='background') {const ledger=new BackgroundJobs(),job=ledger.start(call,{kind,jobId:'J1',output:kind==='promoted'?'initial':''},snapshot);return {ledger,job};}
function end(ledger,job,status='completed',detail='exit code: 1',read=stream()) {return ledger.update(job,{id:'J1',kind:'bash',status,detail},read);}

for(const kind of ['background','promoted'])test(`repair3 ${kind} launch is incomplete and linked, not a success`,()=>{
  const {ledger,job}=start(kind),out=ledger.observation(job);
  assert.equal(out.complete,false);assert.equal(out.exitCode,null);assert.equal(out.jobId,'J1');assert.equal(out.jobStage,'launch');
  assert.equal(job.call.arguments.command,args.command);
});
test('repair3 observer stream supersedes rendered promotion without duplication and retains channels',()=>{
  const {ledger,job}=start('promoted');
  ledger.update(job,{id:'J1',kind:'bash',status:'running'},stream('initial','stdout'));
  const out=end(ledger,job,'completed','exit code: 1',{chunks:[{at:7,text:'err',channel:'stderr'}],next:10,lossy:false});
  assert.equal(out.stdout,'initial');assert.equal(out.stderr,'err');assert.equal(out.complete,true);assert.equal(out.exitCode,1);
  assert.equal(end(ledger,job),null); // at most one terminal execution receipt
});
for(const [status,detail] of [['killed','signal: SIGTERM'],['failed','producer broke'],['completed',''],['completed','exit code: 0 [sandbox: denied]'],['unavailable','unknown job']])test(`repair3 ${status}/${detail} never fabricates a clean outcome`,()=>{
  const {ledger,job}=start(),out=end(ledger,job,status,detail);
  assert.equal(out.complete,false);assert.equal(out.exitCode,null);assert.equal(job.finalized,true);
});
test('repair3 dropped/oversized output remains partial without rejecting or killing execution',()=>{
  for(const read of [{...stream(),lossy:true},stream('x'.repeat(300000),'stdout'),{chunks:[{at:3,text:'tail',channel:'stderr',gapBefore:true}],next:7,lossy:false}]) {
    const {ledger,job}=start(),out=end(ledger,job,'completed','exit code: 1',read);
    assert.equal(out.complete,false);assert.equal(out.jobStage,'final');assert.equal(out.exitCode,1);
  }
});
test('repair3 rendered job_output links failure for review but does not claim full channel coverage',()=>{
  const {ledger,job}=start(),out=ledger.update(job,{id:'J1',kind:'bash',status:'completed',detail:'exit code: 1'},null,'failed');
  assert.equal(out.complete,false);assert.equal(out.exitCode,1);assert.equal(out.outputCoverage,'partial_or_rendered');
});
test('repair3 foreign ID/kind never consumes origin binding',()=>{
  const {ledger,job}=start();
  assert.equal(ledger.update(job,{id:'J2',kind:'bash',status:'completed'},stream()),null);
  assert.equal(ledger.update(job,{id:'J1',kind:'subagent',status:'completed'},stream()),null);
  assert.equal(job.finalized,false);
});
test('repair3 restart invalidates live registry IDs rather than assigning a recycled job outcome',()=>{
  const {ledger}=start();const restored=new BackgroundJobs(JSON.parse(JSON.stringify(ledger.state)));restored.abandon();
  assert.equal(restored.active().length,0);assert.equal(restored.state.items.J1.status,'unavailable');
  assert.equal(end(restored,restored.state.items.J1),null);
});
test('repair3 overlapping jobs have uncertain state attribution',()=>{
  const {ledger,job}=start();ledger.markInterleaved('c2');
  const other=ledger.start({...call,callId:'c2'},{kind:'background',jobId:'J2'},snapshot);
  assert.equal(job.interleaved,true);assert.equal(other.interleaved,true);
});
test('repair3 launch/poll does not consume memory effect or advance check counter; final does',()=>{
  const f=new FullTask({}),p=new Policy(),{ledger,job}=start();
  f.effects.bind(call,{ids:['M1'],decision:'recheck'},S);
  f.observe(call,ledger.observation(job),S,S,deps,deps,p,'launch');
  assert.equal(f.state.observed,0);assert.equal(p.state.memories.length,0);assert.ok(f.effects.state.pending.c1);
  const row=f.observe(call,end(ledger,job),S,S,deps,deps,p,'terminal').row;
  assert.ok(f.state.pendingEvidence.includes(row.id));assert.equal(p.state.memories.length,1);
  assert.equal(f.effects.state.pending.c1,undefined);assert.equal(f.effects.state.stats.outcomes,1);
});
test('repair3 malformed retry items all stay nonfatal and cannot authorize a retry',()=>{
  const f=new FullTask({}),p=new Policy();
  f.observe(call,{executed:true,complete:true,exitCode:1,stdout:'',stderr:'failed'},S,S,deps,deps,p,'raw');
  for(const support of [[null],[1],['bad'],[[]],[{}],[{target:'main.py'}]]) {
    const plan={tool:'bash',arguments:args,evidence_ids:['E1'],strategy_adjustment:'check',memory_review:{decision:'justified_retry',new_evidence:'new',hypothesis:'h',support}};
    p.propose(plan,{visibleEvidence:['E1']});assert.equal(f.before(call,p,S,deps).allowed,false);
  }
  assert.equal(f.state.observed,1);assert.equal(p.state.memories.length,1);
});

async function host(t,{registry=true}={}) {
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const dir=await mkdtemp(path.join(base,'repair3-')),workspace=path.join(dir,'task'),auditDir=path.join(dir,'audit');
  await mkdir(workspace);await writeFile(path.join(workspace,'main.py'),'original');
  const ctx=new Context();await ctx.plugin(LlmRuntime);await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  if(registry){await ctx.plugin(LocalJobs,{});ctx.jobs.attachController('offline-test');}
  await ctx.plugin(plugin,{workspace,auditDir,full:true});t.after(()=>ctx.fiber.dispose());
  let done,producer,id;
  ctx.tools.register({name:'bash',description:'background producer fixture',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'background'}]},execute:()=>{
    id=ctx.jobs.start({kind:'bash',label:'python main.py',run(h){producer=h;return {cancel(){done({status:'killed'});},done:new Promise(r=>done=r)};}});
    producer.append('starting\n',{channel:'stdout'});return {kind:'background',jobId:id};
  }});
  ctx.tools.register({name:'job_output',description:'native cursor reader',parameters:{type:'object'},output:{schema:{type:'object'},render:(_a,v)=>[{type:'text',text:v.text}]},execute:()=>{
    const r=ctx.jobs.read(id);return {text:r.chunks.map(c=>c.text).join(''),job:r.job};
  }});
  ctx.tools.register({name:'write',description:'write fixture',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'written'}]},execute:()=>({ok:true})});
  const agent={session:Session.create('repair3'),ctx:createScope(ctx,{}).ctx};agent.id=agent.session.id;let n=0;
  const execute=(name,arguments_)=>ctx.tools.execute({name,arguments:arguments_,callId:`c${++n}`,agent,signal:new AbortController().signal});
  const state=async()=>{const files=await readdir(auditDir);return JSON.parse(await readFile(path.join(auditDir,files.find(x=>x.endsWith('.json'))),'utf8'));};
  return {ctx,execute,state,agent,workspace,complete:async(exit=1)=>{producer.append(exit?'assertion failed\n':'PASS\n',{channel:exit?'stderr':'stdout'});done({status:'completed',detail:`exit code: ${exit}`});await ctx.jobs.wait(id,1000);},id:()=>id};
}
test('repair3 real DSH registry non-consuming observer preserves model cursor, completes origin exactly once',async t=>{
  const h=await host(t);await h.execute('bash',args);
  const launch=await h.state();assert.ok(Object.values(launch.full.evidence).some(r=>r.jobStage==='launch'));
  assert.equal(launch.state.memories.length,0);
  await h.complete();const output=await h.execute('job_output',{job_id:h.id()});
  assert.match(output.value.text,/starting/);assert.match(output.value.text,/assertion failed/);
  const state=await h.state(),final=Object.values(state.full.evidence).filter(r=>r.jobStage==='final');
  assert.equal(final.length,1);assert.equal(final[0].complete,true);assert.equal(final[0].exitCode,1);
  assert.equal(final[0].command,args.command);assert.ok(state.full.pendingEvidence.includes(final[0].id));
  assert.equal(state.state.memories.length,1);
  await h.execute('job_output',{job_id:h.id()});
  assert.equal(Object.values((await h.state()).full.evidence).filter(r=>r.jobStage==='final').length,1);
});
test('repair3 host INVALID_ARGS rejection clears old proposal before later action',async t=>{
  const h=await host(t),plan={tool:'write',arguments:{file_path:'main.py',content:'fixed'},memory_review:'none yet',strategy_adjustment:'fix',evidence_ids:[]};
  assert.equal((await h.execute('kz_strategy',plan)).isError,false);assert.ok((await h.state()).state.pending);
  h.ctx.on('tools/pre-execute',async(exec,next)=>exec.name==='kz_strategy'?{kind:'deny',reason:'bad parameters',info:{name:'ToolArgumentsError',code:'INVALID_ARGS'}}:next());
  assert.equal((await h.execute('kz_strategy',{tool:42})).isError,true);
  assert.equal((await h.state()).state.pending,null);
});
test('repair3 semantic proposal rejection also clears old pending authorization',async t=>{
  const h=await host(t),plan={tool:'write',arguments:{file_path:'main.py',content:'fixed'},memory_review:'none yet',strategy_adjustment:'fix',evidence_ids:[]};
  await h.execute('kz_strategy',plan);
  assert.equal((await h.execute('kz_strategy',{...plan,evidence_ids:['E999']})).value.accepted,false);
  assert.equal((await h.state()).state.pending,null);
});

test('repair3 real background success verifies only the exact declared stable-target check',async t=>{
  const h=await host(t);
  await h.execute('kz_update',{subgoal_plan:[{id:'G1',title:'main check',acceptance:'public check',targets:['main.py'],depends_on:[],verification:{arguments:args,stdout_contains:['PASS']}}]});
  await h.execute('bash',args);await h.complete(0);await h.execute('job_output',{job_id:h.id()});
  const state=await h.state();assert.equal(state.full.subgoals.items.G1.status,'check_passed');
  assert.equal(Object.values(state.full.evidence).find(r=>r.jobStage==='final').clean,true);
});
test('repair3 background check does not certify a target modified during execution',async t=>{
  const h=await host(t);
  await h.execute('kz_update',{subgoal_plan:[{id:'G1',title:'main check',acceptance:'public check',targets:['main.py'],depends_on:[],verification:{arguments:args,stdout_contains:['PASS']}}]});
  await h.execute('bash',args);await writeFile(path.join(h.workspace,'main.py'),'changed during job');
  await h.complete(0);await h.execute('job_output',{job_id:h.id()});
  assert.notEqual((await h.state()).full.subgoals.items.G1.status,'check_passed');
});
test('repair3 interleaved native action makes background attribution unknown, not a reusable failed anchor',async t=>{
  const h=await host(t);await h.execute('bash',args);
  await h.execute('write',{file_path:'main.py',content:'independent action'});
  await h.complete();await h.execute('job_output',{job_id:h.id()});
  const state=await h.state(),row=Object.values(state.full.evidence).find(r=>r.jobStage==='final');
  assert.equal(row.stateAttribution,'interleaved_unknown');assert.match(row.after,/^unknown:/);
  assert.deepEqual(state.state.memories[0].dependencies,{});assert.match(state.state.memories[0].scope,/^unknown:/);
});
test('repair3 host cancellation of replacement proposal revokes old pending action',async t=>{
  const h=await host(t),plan={tool:'write',arguments:{file_path:'main.py',content:'fixed'},memory_review:'none yet',strategy_adjustment:'fix',evidence_ids:[]};
  await h.execute('kz_strategy',plan);
  h.ctx.on('tools/pre-execute',async(exec,next)=>exec.name==='kz_strategy'?{kind:'cancel'}:next());
  await h.execute('kz_strategy',plan);assert.equal((await h.state()).state.pending,null);
});
test('repair3 matched blocker can be explicitly reviewed as not applicable without demanding unrelated memories',()=>{
  const f=new FullTask({}),p=new Policy();
  f.observe(call,{executed:true,complete:true,exitCode:1,stdout:'',stderr:'failed'},S,S,deps,deps,p,'raw');
  const m=f.memory.admit({kind:'blocker',conclusion:'prior failure',condition:'same file',targets:['main.py'],evidence_ids:['E1']},f.state.evidence,['E1'],S,deps);
  f.state.visibleMemories=[m.id,'M-unrelated'];
  const change={file_path:'main.py',content:'repair'},plan={tool:'write',arguments:change,evidence_ids:['E1'],strategy_adjustment:'repair the source',
    memory_review:{ids:[m.id],decision:'not_applicable',observed_result:'failure',applicability:'old execution is not this source edit',reason:'modify the relevant failing input'}};
  assert.equal(p.propose(plan,{visibleEvidence:['E1']}).accepted,true);
  assert.equal(f.before({name:'write',arguments:change},p,S,deps).allowed,true);
});
