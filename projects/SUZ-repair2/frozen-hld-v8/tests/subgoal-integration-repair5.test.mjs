import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir,mkdtemp,writeFile,readFile,readdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {Context} from '@deepseek-ai/cordis';
import LlmRuntime,{LlmAdapter,createUserMessage} from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import SessionStore from '@deepseek-ai/dsh-session';
import SessionProjections from '@deepseek-ai/dsh-session-projection';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import * as plugin from '../src/plugin.mjs';

const executeFile=promisify(execFile);
const aSource='def add(a, b):\n    """\n    >>> add(1, 2)\n    3\n    """\n    return a + b\n';
const bSource='def double(a):\n    """\n    >>> double(2)\n    4\n    """\n    return a * 2\n';
const aArgs={command:'python -m doctest a.py'},bArgs={command:'python -m doctest b.py'};
const silent=arguments_=>({arguments:arguments_,exit_code:0,stdout_contains:[]});
const plan=[{id:'G1',title:'addition behavior',acceptance:'a.py public doctests pass',targets:['a.py'],depends_on:[]},
  {id:'G2',title:'dependent doubling behavior',acceptance:'b.py public doctests pass after addition is verified',targets:['b.py'],depends_on:['G1'],verification:silent(bArgs)}];

class LifecycleAdapter extends LlmAdapter {
  requests=[];snapshots=[];
  constructor(state){super();this.state=state;}
  async resolveModel(provider,model){return {provider,id:model,name:model};}
  async *stream(options) {
    assert.equal(options.system,undefined,'No auxiliary model is needed for this deterministic scheduling test');
    this.requests.push(options);const step=this.requests.length,current=await this.state();this.snapshots.push(current);
    if(step===1) {
      assert.match(JSON.stringify(options),/Establish concrete subgoals/);
      assert.equal(current.full.subgoalController.planPrompts,1);assert.equal(current.full.subgoalControl.blocking,false);
    }
    if(step===3) {
      assert.equal(current.full.evidence.E1.stdout,'');assert.equal(current.full.evidence.E1.exitCode,0);
      assert.equal(current.full.evidence.E1.complete,true);assert.equal(current.full.evidence.E1.clean,true);
      assert.deepEqual(current.full.evidence.E1.arguments,aArgs);
      assert.equal(current.full.subgoals.items.G1.status,'pending');
      assert.equal(current.full.subgoalControl.verification_candidates[0].evidence_id,'E1');
      assert.match(JSON.stringify(options),/do not invent a success marker/);
    }
    if(step===4) {
      assert.equal(current.full.subgoals.items.G1.status,'check_passed');assert.equal(current.full.subgoals.items.G1.proof.evidence,'E1');
      assert.equal(current.full.subgoals.active,'G2');assert.equal(current.full.subgoalControl.active,'G2');
    }
    if(step===5) {
      assert.equal(current.full.subgoals.items.G2.status,'check_passed');assert.equal(current.full.subgoals.active,null);
      assert.equal(current.full.subgoalControl.mode,'planned_checks_passed');assert.equal(current.full.subgoalControl.official_success,null);
    }
    if(step===6) {
      assert.equal(current.full.subgoals.items.G1.status,'needs_recheck');assert.equal(current.full.subgoals.items.G1.proof,null);
      assert.equal(current.full.subgoals.items.G2.status,'needs_recheck');assert.equal(current.full.subgoals.items.G2.proof,null);
      assert.equal(current.full.subgoals.active,'G1');assert.equal(current.full.subgoalControl.active,'G1');
    }
    const actions=[
      {name:'kz_update',args:{subgoal_plan:plan}},
      {name:'bash',args:aArgs},
      {name:'kz_update',args:{subgoal_update:{id:'G1',reason:'Public doctest was observed to complete silently',expected_revision:1,verification:silent(aArgs)},verification_evidence:{subgoal_id:'G1',evidence_id:'E1',revision:2}}},
      {name:'bash',args:bArgs},
      {name:'write',args:{file_path:'a.py',content:aSource.replace('return a + b','return a - b')}},
      'A source change invalidated the checks. Both goals honestly remain unverified until a recheck.'
    ];
    const action=actions[step-1];if(!action)throw new Error('unexpected extra solver request');
    const block=typeof action==='string'?{type:'text',text:action}:{type:'tool-call',id:`subgoal-r5-${step}`,name:action.name,arguments:JSON.stringify(action.args)};
    yield{type:'block-start',index:0,blockType:block.type};
    if(block.type==='text')yield{type:'text-delta',index:0,text:block.text};else yield{type:'tool-call-delta',index:0,id:block.id,name:block.name,argumentsDelta:block.arguments};
    yield{type:'block-end',index:0,block};yield{type:'usage',usage:{inputTokens:10,outputTokens:5}};yield{type:'finish',reason:{kind:block.type==='text'?'stop':'tool-calls'}};
  }
}

test('R5 official DSH loop: early plan → real silent doctest → explicit E binding → next goal → source edit invalidates dependent proofs',{timeout:20000},async t=>{
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const dir=await mkdtemp(path.join(base,'subgoal-integration-r5-')),workspace=path.join(dir,'task'),auditDir=path.join(dir,'audit');await mkdir(workspace);
  await writeFile(path.join(workspace,'a.py'),aSource);await writeFile(path.join(workspace,'b.py'),bSource);
  const ctx=new Context();await ctx.plugin(LlmRuntime);await ctx.plugin(SessionStore);await ctx.plugin(SessionProjections);await ctx.plugin(AgentRegistry);
  await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(plugin,{workspace,auditDir,full:true,maxRequests:20,maxTools:20,monitorEnabled:false,criticEnabled:false,backtracking:false});
  await ctx.plugin(AgentLoop,{agents:[],maxParallelToolCalls:1});t.after(()=>ctx.fiber.dispose());
  let actualChecks=0,writes=0;
  // Uses actual DSH ToolRuntime and a real Python doctest child process; the
  // platform shell transport is a deterministic fixture, not production Bash.
  ctx.tools.register({name:'bash',description:'Run only the two public doctest fixtures',parameters:{type:'object',additionalProperties:true},isConcurrencySafe:()=>false,
    output:{schema:{type:'object'},render:(_args,value)=>[{type:'text',text:value.stdout.text||`Process exited with code ${value.exitCode}; stdout is empty.`}]},
    async execute(args) {
      assert.ok([aArgs.command,bArgs.command].includes(args.command));actualChecks++;
      const output=await executeFile(process.platform==='win32'?'python':'python3',['-m','doctest',args.command.split(' ').at(-1)],{cwd:workspace});
      return {kind:'foreground',exitCode:0,timedOut:false,aborted:false,stopped:false,signal:null,stdout:{text:output.stdout,truncated:false},stderr:{text:output.stderr,truncated:false}};
    }});
  ctx.tools.register({name:'write',description:'Update the public addition fixture',parameters:{type:'object',additionalProperties:true},isConcurrencySafe:()=>false,
    output:{schema:{type:'object'},render:()=>[{type:'text',text:'File written.'}]},
    async execute(args){assert.equal(args.file_path,'a.py');writes++;await writeFile(path.join(workspace,args.file_path),args.content);return {written:true};}});
  const state=async()=>{const files=await readdir(auditDir);return JSON.parse(await readFile(path.join(auditDir,files.find(file=>file.endsWith('.json'))),'utf8'));};
  const adapter=new LifecycleAdapter(state);ctx.llm.registerAdapter(['subgoal-r5-fixture'],adapter);
  const agent=await ctx.agentLoop.create('subgoal-lifecycle',{provider:'subgoal-r5-fixture',model:'fixture'},{cwd:workspace});
  const idle=new Promise(resolve=>{const dispose=ctx.on('agent/status',({agent:who,status})=>{if(who===agent&&status==='idle'){dispose();resolve();}});});
  agent.followup(createUserMessage({content:[{type:'text',text:'Implement the public addition and dependent doubling behavior. Verify their public doctests; a changed implementation needs rechecking.'}],source:{kind:'user'}}));await idle;
  assert.equal(adapter.requests.length,6);assert.equal(actualChecks,2);assert.equal(writes,1);
  const final=await state();assert.equal(final.full.usage.requests,6);assert.deepEqual(final.full.usage.roles,{solver:6});assert.equal(final.full.subgoalController.planPrompts,1);
  assert.equal(final.full.subgoals.items.G1.checks,1);assert.equal(final.full.subgoals.items.G2.checks,1);assert.equal(final.full.rollbacks,0);
  const files=await readdir(auditDir),events=(await readFile(path.join(auditDir,files.find(file=>file.endsWith('.jsonl'))),'utf8')).trim().split('\n').map(JSON.parse);
  assert.deepEqual(events.filter(event=>event.event==='subgoal_focus_changed').map(event=>event.active),['G1','G2',null,'G1']);
  assert.equal(events.filter(event=>event.event==='subgoal_plan_requested').length,1);
  assert.ok(events.some(event=>event.event==='subgoal_verification_candidates'&&event.candidates.some(candidate=>candidate.evidence_id==='E1')));
});
