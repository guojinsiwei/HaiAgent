import test from 'node:test';
import assert from 'node:assert/strict';
import { Context } from '@deepseek-ai/cordis';
import SystemPrompt, { renderContextSections } from '@deepseek-ai/dsh-system-prompt';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import LlmRuntime from '@deepseek-ai/dsh-llm';
import { Session } from '@deepseek-ai/dsh-session';
import { createScope, scopeOf } from '@deepseek-ai/dsh-scope';
import { mkdtemp, mkdir, writeFile, readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import * as plugin from '../src/plugin.mjs';

const args={command:'python check.py',description:'public check'};
const outcome=exitCode=>({kind:'foreground',exitCode,timedOut:false,aborted:false,signal:null,
  stdout:{text:exitCode?'':'public check passed',truncated:false},stderr:{text:exitCode?'assertion failed':'',truncated:false}});
const proposal=(extra={})=>({tool:'bash',arguments:args,execute:true,memory_review:'No currently relevant memory.',strategy_adjustment:'Run the public check.',evidence_ids:[],...extra});

async function fixture(t,options={}) {
  const runtime=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(runtime,{recursive:true});
  const base=await mkdtemp(path.join(runtime,'strategy-repair4-')),workspace=path.join(base,'task'),auditDir=path.join(base,'audit');
  await mkdir(workspace);await writeFile(path.join(workspace,'check.py'),'original');
  const ctx=new Context();await ctx.plugin(LlmRuntime);await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(plugin,{workspace,auditDir,full:true,monitorEnabled:false,criticEnabled:false,...options});
  let executions=0,reads=0,serial=0;
  ctx.tools.register({name:'bash',description:'Offline scripted shell DTO, no process or network',parameters:{type:'object',additionalProperties:true},
    output:{schema:{type:'object',additionalProperties:true},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},isConcurrencySafe:()=>false,
    execute:async()=>{executions++;return outcome(options.exitCode??0);}});
  ctx.tools.register({name:'read',description:'Offline public source page fixture',parameters:{type:'object',additionalProperties:true},
    output:{schema:{type:'object',additionalProperties:true},render:(_a,v)=>[{type:'text',text:v.text}]},isConcurrencySafe:()=>false,
    execute:async a=>{reads++;return {text:`observed source page ${a.offset??0}`};}});
  const session=Session.create('strategy-repair4'),agent={id:session.id,session,ctx:createScope(ctx,{}).ctx};
  const execute=(name,arguments_,who=agent,signal=new AbortController().signal)=>ctx.tools.execute({name,arguments:arguments_,callId:`fixture-${++serial}`,agent:who,signal});
  const panel=async(who=agent)=>JSON.parse(renderContextSections(await ctx.systemPrompt.assemble({scope:scopeOf(who.ctx)})).find(x=>x.name==='kz:evidence').text);
  const checkpoints=async()=>Promise.all((await readdir(auditDir)).filter(x=>x.endsWith('.json')).map(async x=>JSON.parse(await readFile(path.join(auditDir,x),'utf8'))));
  const events=async()=> (await Promise.all((await readdir(auditDir)).filter(x=>x.endsWith('.jsonl')).map(x=>readFile(path.join(auditDir,x),'utf8')))).flatMap(text=>text.trim().split('\n').filter(Boolean).map(x=>JSON.parse(x)));
  t.after(()=>ctx.fiber.dispose());
  return {ctx,agent,workspace,auditDir,execute,panel,checkpoints,events,executions:()=>executions,reads:()=>reads};
}

test('repair4 strategy execute:true traverses actual DSH runtime exactly once and exposes native receipt',{timeout:10000},async t=>{
  const f=await fixture(t);const result=await f.execute('kz_strategy',proposal());
  assert.equal(result.isError,false);assert.equal(result.value.accepted,true);assert.equal(f.executions(),1);
  assert.equal(result.value.execution.receipt.isError,false);assert.equal(result.value.execution.receipt.value.exitCode,0);
  assert.match(result.value.execution.callId,/:action$/);
  const [saved]=await f.checkpoints();assert.equal(saved.state.pending,null);
  assert.equal(saved.full.usage.tools,2,'wrapper and actual native action are both counted');
  assert.equal(Object.keys(saved.full.evidence).length,1);assert.equal(saved.full.evidence.E1.tool,'bash');
  assert.equal((await f.events()).filter(x=>x.event==='strategy_execution_receipt').length,1);
});

test('exploration learning traverses real schema, execution, audit, persistence and next prompt',async t=>{
  const f=await fixture(t,{exitCode:1});
  await f.execute('bash',args);await f.execute('bash',args);
  assert.equal((await f.panel()).exploration.active,true);
  for(let i=0;i<10;i++)await f.execute('read',{file_path:'check.py',offset:i});
  assert.equal((await f.panel()).exploration.episode.executions,0);
  const result=await f.execute('kz_strategy',proposal({arguments:{command:'ss -lnt'},
    orthogonality_proof:{dependency_dimension:'same environment',target_dimension:'inspect sockets',command_dimension:'same shell'},
    changed_dimensions:['target_dimension'],exploration:{hypothesis:'listener is present',
      supports:{field:'stdout',contains:'LISTEN'},refutes:{field:'stderr',contains:'assertion failed'}}}));
  assert.equal(result.value.accepted,true);assert.equal(f.executions(),2);
  const panel=await f.panel();assert.equal(panel.exploration.results[0].status,'refuted');
  assert.equal(panel.exploration.episode.executions,1);
  const [saved]=await f.checkpoints();assert.equal(saved.state.experiments[0].evidence_id,panel.exploration.results[0].evidence_id);
  assert.equal((await f.events()).filter(e=>e.event==='exploration_learning').length,1);
  const history=await f.execute('kz_history',{id:'context'});
  assert.match(history.value.text,/exploration_results/);
});

test('repair4 declaration-only compatibility remains: execute omitted never invokes native action',async t=>{
  const f=await fixture(t),plan=proposal();delete plan.execute;
  const declared=await f.execute('kz_strategy',plan);assert.equal(declared.value.accepted,true);assert.equal(f.executions(),0);assert.equal(declared.value.execution,undefined);
  assert.equal((await f.execute('bash',args)).isError,false);assert.equal(f.executions(),1);
});

test('repair4 atomic strategy does not bypass the final duplicate failure gate',async t=>{
  const f=await fixture(t,{exitCode:1});assert.equal((await f.execute('kz_strategy',proposal())).value.execution.receipt.value.exitCode,1);
  const second=await f.execute('kz_strategy',proposal({evidence_ids:['E1']}));
  assert.equal(second.value.accepted,true,'proposal acceptance is not native execution approval');
  assert.equal(second.value.execution.receipt.isError,true);assert.equal(f.executions(),1);
  assert.match(JSON.stringify(second.value.execution.receipt),/same_failed_command_in_unchanged_workspace/);
  const [saved]=await f.checkpoints();assert.equal(saved.state.pending,null);assert.equal(Object.keys(saved.full.evidence).length,1);
});

test('repair4 atomic strategy cannot overrule host permission denial',async t=>{
  const f=await fixture(t);
  f.ctx.on('tools/pre-execute',async(exec,next)=>exec.name==='bash'?{kind:'deny',reason:'host-permission-denied'}:next());
  const result=await f.execute('kz_strategy',proposal());assert.equal(f.executions(),0);
  assert.equal(result.value.execution.receipt.isError,true);assert.match(JSON.stringify(result.value.execution.receipt),/host-permission-denied/);
  const [saved]=await f.checkpoints();assert.equal(saved.state.pending,null);assert.equal(Object.keys(saved.full.evidence).length,0);
});

test('repair4 atomic strategy cannot overrule cancellation at the child action boundary',async t=>{
  const f=await fixture(t),control=new AbortController();
  f.ctx.on('tools/pre-execute',async(exec,next)=>{if(exec.name==='bash'){control.abort();return {kind:'cancel'};}return next();});
  const result=await f.execute('kz_strategy',proposal(),f.agent,control.signal);
  assert.equal(f.executions(),0);assert.ok(result.isError||result.value?.execution?.receipt?.isError);
  const [saved]=await f.checkpoints();assert.equal(saved.state.pending,null);assert.equal(Object.keys(saved.full.evidence).length,0);
});

test('repair4 shared tool cap includes the wrapper and prevents an unbudgeted child execution',async t=>{
  const f=await fixture(t,{maxTools:1});const result=await f.execute('kz_strategy',proposal());
  assert.equal(f.executions(),0);assert.equal(result.value.execution.receipt.isError,true);
  assert.match(JSON.stringify(result.value.execution.receipt),/tool budget/);
  const [saved]=await f.checkpoints();assert.equal(saved.full.usage.tools,1);assert.equal(saved.state.pending,null);
});

test('repair4 ordinary action has no empty memory declaration requirement',async t=>{
  const f=await fixture(t);await f.execute('read',{file_path:path.join(f.workspace,'check.py')});
  const panel=await f.panel();assert.equal(panel.memory_action_contract.required,false);assert.deepEqual(panel.memory_action_contract.visible_ids,[]);
  assert.match(panel.memory_action_contract.instruction,/ordinary native tools directly/);
  assert.equal((await f.execute('bash',args)).isError,false);assert.equal(f.executions(),1);
});

test('repair4 real old evidence remains usable after display omission and archive eviction',{timeout:20000},async t=>{
  const f=await fixture(t);
  for(let i=0;i<68;i++)await f.execute('read',{file_path:path.join(f.workspace,'check.py'),offset:i});
  const before=await f.panel();assert.ok(!before.evidence.some(x=>x.id==='E1'));
  const [initial]=await f.checkpoints();assert.equal(initial.full.evidence.E1,undefined,'E1 genuinely left the bounded active store');
  const result=await f.execute('kz_strategy',proposal({execute:false,evidence_ids:['E1']}));
  assert.equal(result.value.accepted,true);assert.equal(f.executions(),0);
  assert.ok((await f.events()).some(x=>x.event==='evidence_reference_loaded'&&x.id==='E1'));
  const [saved]=await f.checkpoints();assert.equal(saved.full.evidence.E1.stdout,'observed source page 0');
  const memory=await f.execute('kz_update',{memory:{kind:'finding',conclusion:'The original public source page was observed.',condition:'Historical source observation; inspect again after changes.',targets:[path.join(f.workspace,'check.py')],evidence_ids:['E1']}});
  assert.equal(memory.value.memory.id,'M1');assert.deepEqual(memory.value.memory.targets,['check.py']);
});

test('repair4 future and another session evidence cannot authorize an atomic action',async t=>{
  const f=await fixture(t);await f.execute('read',{file_path:path.join(f.workspace,'check.py')});
  const future=await f.execute('kz_strategy',proposal({evidence_ids:['E999']}));assert.equal(future.value.accepted,false);assert.equal(future.value.execution,undefined);
  const session=Session.create('another-strategy-task'),other={id:session.id,session,ctx:createScope(f.ctx,{}).ctx};
  const foreign=await f.execute('kz_strategy',proposal({evidence_ids:['E1']}),other);
  assert.equal(foreign.value.accepted,false);assert.equal(foreign.value.execution,undefined);assert.equal(f.executions(),0);
  assert.match(foreign.value.reason,/real, already-observed task evidence/);
});
