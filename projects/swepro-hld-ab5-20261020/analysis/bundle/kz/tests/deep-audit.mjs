// Acceptance contracts intentionally separate from the existing regression suite.
// Failures here are audit findings, not silently blessed snapshots of wrong behavior.
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, readdir, open } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { Context } from '@deepseek-ai/cordis';
import LlmRuntime from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import { Session } from '@deepseek-ai/dsh-session';
import { createScope, scopeOf } from '@deepseek-ai/dsh-scope';
import * as plugin from '../src/plugin.mjs';
import { Policy } from '../src/policy.mjs';
import { FullTask } from '../src/full-task.mjs';
import { fingerprint } from '../src/workspace.mjs';
import { classify, extractStream } from '../src/terminal.mjs';

const command={command:'python check.py',description:'check implementation'};
const dto=(exit=1,text='missing dependency')=>({kind:'foreground',exitCode:exit,signal:null,timedOut:false,aborted:false,stdout:{text:exit?'':text,truncated:false},stderr:{text:exit?text:'',truncated:false}});
async function fixture(t,options={}) {
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const dir=await mkdtemp(path.join(base,'deep-audit-')),workspace=path.join(dir,'task'),audit=path.join(dir,'audit');
  await mkdir(workspace);await writeFile(path.join(workspace,'check.py'),'original');
  const ctx=new Context();await ctx.plugin(LlmRuntime);await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(plugin,{workspace,auditDir:audit,full:true,monitorCooldown:1000,...options});
  let executions=0;
  ctx.tools.register({name:'bash',description:'offline DTO fixture',parameters:{type:'object',additionalProperties:true},output:{schema:{type:'object'},render:(_a,v)=>[{type:'text',text:v.stdout.text+v.stderr.text}]},isConcurrencySafe:()=>false,
    execute:()=>{executions++;return options.outcome??dto();}});
  ctx.tools.register({name:'read',description:'offline native read fixture',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'defective code evidence'}]},execute:()=>({text:'defective code evidence'})});
  const agent={session:Session.create('deep-audit'),ctx:createScope(ctx,{}).ctx};agent.id=agent.session.id;
  let call=0;const execute=(name='bash',args=command,who=agent)=>ctx.tools.execute({name,arguments:args,callId:`audit-${++call}`,agent:who,signal:new AbortController().signal});
  const state=async()=>{const files=await readdir(audit);return JSON.parse(await readFile(path.join(audit,files.find(x=>x.endsWith('.json'))),'utf8'));};
  const panel=()=>ctx.systemPrompt.assemble({scope:scopeOf(agent.ctx)});
  t.after(()=>ctx.fiber.dispose());return{ctx,workspace,audit,agent,execute,state,panel,executions:()=>executions};
}
const memory=id=>({kind:'blocker',conclusion:'Check failed on this source',condition:'observed check.py only',targets:['check.py'],evidence_ids:[id]});

test('PASS01 visible evidence can generate, retrieve and bind a conditional memory in the actual host',async t=>{
  const f=await fixture(t);await f.execute();await f.panel();
  const created=await f.execute('kz_update',{memory:memory('E1')});assert.equal(created.value.memory.id,'M1');
  const prompt=await f.panel();assert.match(JSON.stringify(prompt),/M1/);
  const retrieval=await f.execute('kz_history',{id:'M1'});assert.equal(retrieval.isError,false);assert.match(retrieval.value.text,/check.py/);
  const different={...command,command:'node alternative.js'};
  const blocked=await f.execute('bash',different);assert.equal(blocked.isError,true);assert.equal(f.executions(),1);
  const proposal=await f.execute('kz_strategy',{tool:'bash',arguments:different,evidence_ids:['E1'],strategy_adjustment:'test different implementation',memory_review:{ids:['M1'],observed_result:'failed',applicability:'same source',decision:'different_route',reason:'check alternative implementation'}});
  assert.equal(proposal.value.accepted,true);assert.equal((await f.execute('bash',different)).isError,false);assert.equal(f.executions(),2);
});
test('PASS02 host recreates full task memory and metadata without leaking into a fresh session',async t=>{
  const f=await fixture(t);await f.execute();await f.panel();await f.execute('kz_update',{memory:memory('E1')});
  const restored={id:'deep-audit',session:Session.create('deep-audit'),ctx:createScope(f.ctx,{}).ctx};
  assert.equal((await f.execute('kz_history',{id:'M1'},restored)).isError,false);
  const fresh={id:'fresh-audit',session:Session.create('fresh-audit'),ctx:createScope(f.ctx,{}).ctx};
  assert.equal((await f.execute('kz_history',{id:'M1'},fresh)).isError,true);
});
test('PASS03 long terminal evidence is paginated without dropping the middle',async t=>{
  const content='a'.repeat(15000)+'UNIQUE_MIDDLE_EVIDENCE'+'z'.repeat(15000);
  const f=await fixture(t,{outcome:dto(0,content)});await f.execute();
  let offset=0,joined='';do{const r=await f.execute('kz_history',{id:'E1',offset});assert.equal(r.isError,false);joined+=r.value.text;offset=r.value.next_offset;}while(offset!==null);
  assert.match(joined,/UNIQUE_MIDDLE_EVIDENCE/);assert.equal(JSON.parse(joined).native.value.stdout.text,content);
});
test('GAP01 native read results should enter KZ evidence, not only the host transcript',async t=>{
  const f=await fixture(t);for(let i=0;i<15;i++)await f.execute('read',{path:'check.py'});
  const s=await f.state();assert.ok(Object.values(s.full.evidence).some(r=>JSON.stringify(r).includes('defective code evidence')),
    '15 successful native reads produced zero KZ evidence rows; observed='+s.full.observed);
});
test('GAP02 known unchanged file reads are reusable; arbitrary successful programs are not automatically useless',async t=>{
  const f=await fixture(t,{outcome:dto(0,'same output')});for(let i=0;i<5;i++)await f.execute('bash',{...command,command:'cat check.py'});
  assert.equal(f.executions(),1,'unchanged file was read repeatedly without new conditions');
});
test('GAP03 changing an unrelated file should not count as repairing a recorded command dependency',async t=>{
  const f=await fixture(t);await f.execute();await writeFile(path.join(f.workspace,'irrelevant.txt'),'cosmetic change');
  const retry=await f.execute();assert.equal(retry.isError,true,'unrelated write permitted exact failed retry; check.py unchanged');
});
test('GAP04 evidence explicitly read via kz_history should be usable as a memory source',async t=>{
  const f=await fixture(t,{outcome:dto(0,'complete public observation')});
  for(let i=1;i<=8;i++)await f.execute('bash',{...command,command:`python observation${i}.py`});
  await f.panel();assert.equal((await f.execute('kz_history',{id:'E1'})).isError,false);
  const result=await f.execute('kz_update',{memory:memory('E1')});
  assert.ok(result.value.memory.id,'history read succeeded but admission failed: '+JSON.stringify(result.value));
});
test('GAP05 failure evidence should remain eligible until Monitor sees it, not expire before first trigger',()=>{
  const task=new FullTask({}),policy=new Policy();let first=null;
  for(let i=1;i<=24;i++){
    task.observe({name:'bash',arguments:{command:`python check${i}.py`}},
      {executed:true,complete:true,exitCode:i===1?1:0,stdout:i===1?'failure':'ordinary information',stderr:''},'sha256:fixed','sha256:fixed',{},{},policy,`raw${i}`);
    if(task.monitorDue()&&!first)first={step:i,supplied:Object.keys(task.state.evidence).slice(-16)};
  }
  assert.ok(first?.supplied.includes('E1'),'first monitor opportunity='+JSON.stringify(first)+'; original failure no longer supplied');
});
test('GAP06 configured recall limit should control full mode, not be ignored',()=>{
  const task=new FullTask({recallLimit:1}),policy=new Policy();task.state.scope='sha256:fixed';task.state.taskGoal='repair parser';
  for(let i=1;i<=4;i++){const id=`E${i}`;task.state.evidence[id]={id,complete:true,after:'sha256:fixed',stdout:'parser',stderr:'',command:'parser',category:'generic'};task.memory.admit({kind:'finding',conclusion:`parser observation ${i}`,condition:'same environment',targets:[],evidence_ids:[id]},task.state.evidence,[id],'sha256:fixed',{});}
  assert.equal(task.panel(policy).result.memories.length,1,'full context hardcodes recall limit 4');
});
test('FROZEN07 >64 MiB observation remains unknown; no false snapshot or automatic recovery is claimed',async t=>{
  const f=await fixture(t);const file=await open(path.join(f.workspace,'build-artifact.bin'),'w');try{await file.truncate(65*1024*1024);}finally{await file.close();}
  assert.match(await fingerprint(f.workspace),/^unknown:/);
  await f.execute();const state=await f.state();assert.deepEqual(state.full.checkpoints,[]);assert.equal(state.full.pendingRollback,null);
  // Original GAP07 is deferred by user decision, NOT a repaired large-tree snapshot.
});
test('GAP08 common compound CLI test should retain a middle diagnostic in its extracted view',()=>{
  const cmd='cd project && make test',lines=Array.from({length:1000},(_,i)=>`build noise ${i}`);lines[500]='UNIQUE_ERROR_MIDDLE: failed assertion';
  assert.match(extractStream(lines.join('\n'),classify(cmd),1800),/UNIQUE_ERROR_MIDDLE/,'compound command classified generic, only head/tail survive');
});
test('PASS04 simple AND-chain public check can pass declared assertions',()=>{
  const task=new FullTask({}),policy=new Policy();task.goals.define({subgoal_plan:[{id:'G1',title:'check',acceptance:'public test',depends_on:[],targets:['check.py'],verification:{arguments:{command:'cd project && make test'},stdout_contains:['passed']}}]});
  task.observe({name:'bash',arguments:{command:'cd project && make test'}},{executed:true,complete:true,exitCode:0,stdout:'passed',stderr:''},'sha256:x','sha256:x',{'check.py':'file:a'},{'check.py':'file:a'},policy,'raw');
  assert.equal(task.goals.state.items.G1.status,'check_passed','all compound commands treated as unknown status; stage receipts are not collected');
});
test('GAP09 a quoted semicolon argument should not be mistaken for a shell pipeline',()=>{
  const task=new FullTask({}),policy=new Policy(),args={command:'python check.py --case "a;b"'};
  task.goals.define({subgoal_plan:[{id:'G1',title:'quoted argument',acceptance:'public test',depends_on:[],targets:['check.py'],verification:{arguments:args,stdout_contains:['passed']}}]});
  task.observe({name:'bash',arguments:args},{executed:true,complete:true,exitCode:0,stdout:'passed',stderr:''},'sha256:x','sha256:x',{'check.py':'file:a'},{'check.py':'file:a'},policy,'raw');
  assert.equal(task.goals.state.items.G1.status,'check_passed','literal semicolon inside quoted argument is treated as unknown shell-stage status');
});
test('GAP11 monitor must reserve review capacity for the latter part of a 600-step task',()=>{
  const task=new FullTask({maxTools:600}),policy=new Policy();
  for(let i=1;i<=96;i++){
    task.observe({name:'bash',arguments:{command:`python failure${i}.py`}},{executed:true,complete:true,exitCode:1,stdout:'failed',stderr:''},'sha256:fixed','sha256:fixed',{},{},policy,`raw${i}`);
    if(task.monitorDue())task.monitorStarted();
  }
  assert.ok(task.state.monitorCalls<=6,`all ${task.state.monitorCalls}/12 reviews consumed by observed step 96/600`);
});
test('GAP10 old turn-history literal search contract should remain accessible',async t=>{
  const f=await fixture(t);await f.execute();const result=await f.execute('kz_history',{query:'missing dependency'});
  assert.equal(result.isError,false,'only known E/M IDs or context are supported; old turn/query retrieval not ported');
});

test('REPAIR history retrieval beyond the active 64 rows remains citable after prompt reassembly',async t=>{
  const f=await fixture(t,{outcome:dto(0,'original historical finding')});for(let i=0;i<70;i++)await f.execute('bash',{command:`python observation${i}.py`});
  assert.ok(!(await f.state()).full.evidence.E1);
  assert.equal((await f.execute('kz_history',{id:'E1'})).isError,false);await f.panel();
  const admitted=await f.execute('kz_update',{memory:memory('E1')});assert.ok(admitted.value.memory.id);
  const search=await f.execute('kz_history',{query:'original historical finding'});assert.equal(search.value.matches.length,8);assert.ok(search.value.next_offset!==null);
  const turns=await f.execute('kz_history',{turn:0});assert.equal(turns.isError,false);assert.ok(turns.value.matches.every(r=>r.turn===0));
});
