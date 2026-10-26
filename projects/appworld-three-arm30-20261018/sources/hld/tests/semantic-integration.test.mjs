import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdir,mkdtemp,writeFile,readFile,readdir} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import LlmRuntime,{LlmAdapter,createUserMessage} from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import SessionStore from '@deepseek-ai/dsh-session';
import SessionProjections from '@deepseek-ai/dsh-session-projection';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import * as plugin from '../src/plugin.mjs';
import {renderConfig} from '../scripts/prepare-config.mjs';
import {parse} from 'yaml';

const action=command=>({name:'bash',args:{command,description:'offline public observation'}});
const scout=[action('pwd'),action('ls'),action('cat task.txt')];
const route=(id,hypothesis,mechanism,target)=>({id,hypothesis,mechanism,target,
  steps:['inspect the relevant public boundary','repair based on evidence','rerun original public test'],
  progress_signal:'targeted public boundary check improves',abandon_when:'premise refuted by public observation',evidence_ids:['E1']});
const fixtureRoutes=[route('D1','parser discards a boundary','trace tokenizer and repair parser','parser'),route('D2','serializer discards a boundary','trace roundtrip and repair writer','serializer')];
const assess=(rs,id)=>rs.map(r=>({route_id:r.id,suitability:r.id===id?0.9:0.4,disposition:'retain',reason:'compare public evidence and expected progress',evidence_ids:[]}));
const plan=()=>({task_model:{problem:'preserve public roundtrip behavior',environment:'public task and source files',unknowns:['where loss occurs']},
  routes:structuredClone(fixtureRoutes),evaluations:assess(fixtureRoutes,'D1'),selected_route_id:'D1',reason:'diagnose input boundary first',evidence_ids:['E1']});
const switchPlan=p=>{
  const fresh={...route(p.next_route_id,`loss at ${p.next_route_id} boundary`,`inspect independent ${p.next_route_id} subsystem`,'intermediate buffer'),evidence_ids:[]};
  const selected=p.active_route_id==='D1'?p.routes.find(r=>r.id==='D2'):fresh;
  return{routes:[fresh],evaluations:assess([...p.routes,fresh],selected.id),selected_route_id:selected.id,reason:'compare old and new directions against recent observations',evidence_ids:p.trigger.evidence_ids,
    contrast:{dimension:'mechanism',previous:p.routes.find(r=>r.id===p.active_route_id).mechanism,next:selected.mechanism,reason:'test a different subsystem and causal mechanism'}};
};
const dto=(command)=>({kind:'foreground',exitCode:command.includes('fail')?1:0,timedOut:false,aborted:false,signal:null,
  stdout:{text:command.includes('fail')?'':'public files /app parser serializer',truncated:false},
  stderr:{text:command.includes('fail')?'AssertionError: public behavior is still wrong':'',truncated:false}});

class Adapter extends LlmAdapter {
  constructor(script,options={}){super();this.script=script;this.options=options;this.solver=0;this.requests=[];this.roles=[];}
  async resolveModel(provider,model){return{provider,id:model,name:model};}
  async *stream(options){
    this.requests.push(options);let block;
    if(options.system){
      const p=JSON.parse(options.messages[0].content[0].text);let answer;
      if(['initial_plan','route_review'].includes(p.stage)){
        this.roles.push({role:'semantic_planner',payload:p});
        answer=this.options.badPlanner?'invalid JSON':JSON.stringify(p.stage==='initial_plan'?plan():switchPlan(p));
      }else if(p.question){
        this.roles.push({role:'advisor',payload:p});
        answer=JSON.stringify({alternatives:[{hypothesis:'observe public input boundary',check:'read source',difference:'inspect input',evidence_ids:[]}]});
      }else{
        this.roles.push({role:'monitor',payload:p});
        const ids=Object.values(p.evidence).filter(r=>r.semanticRoute==='D1').map(r=>r.id).slice(-2);
        answer=JSON.stringify({verdict:ids.length>=2?'stalled':'uncertain',reason:'public observations do not show progress',
          evidence_ids:ids.length>=2?ids:Object.keys(p.evidence).slice(-1),control_ids:[],next_check:'inspect serialization boundary',memories:[]});
      }
      block={type:'text',text:answer};
    }else{
      let step=this.script[this.solver++];assert.ok(step,'unexpected Solver request');
      if(typeof step==='function')step=step(options);
      block=typeof step==='string'?{type:'text',text:step}:{type:'tool-call',id:`semantic-${this.solver}`,name:step.name,arguments:JSON.stringify(step.args)};
    }
    yield{type:'block-start',index:0,blockType:block.type};
    yield block.type==='text'?{type:'text-delta',index:0,text:block.text}:{type:'tool-call-delta',index:0,id:block.id,name:block.name,argumentsDelta:block.arguments};
    yield{type:'block-end',index:0,block};
    yield{type:'usage',usage:{inputTokens:10,outputTokens:5}};
    yield{type:'finish',reason:{kind:block.type==='text'?'stop':'tool-calls'}};
  }
}

async function host(t,config={}){
  const runtime=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(runtime,{recursive:true});
  const base=await mkdtemp(path.join(runtime,'semantic-')),workspace=path.join(base,'task'),auditDir=path.join(base,'audit');
  await mkdir(workspace);await writeFile(path.join(workspace,'task.txt'),'Implement the public roundtrip behavior.');
  const ctx=new Context();
  await ctx.plugin(LlmRuntime);await ctx.plugin(SessionStore);await ctx.plugin(SessionProjections);await ctx.plugin(AgentRegistry);
  await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(plugin,{workspace,auditDir,full:true,semanticPlannerEnabled:true,criticEnabled:false,monitorEnabled:false,
    maxRequests:30,maxTools:50,advisorCooldownTools:5,...config});
  await ctx.plugin(AgentLoop,{agents:[],maxParallelToolCalls:1});
  const executed=[];
  ctx.tools.register({name:'bash',description:'offline native DTO fixture; no process',parameters:{type:'object',additionalProperties:true},isConcurrencySafe:()=>false,
    output:{schema:{type:'object',additionalProperties:true},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},
    execute:async args=>{executed.push(args.command);return dto(args.command);}});
  t.after(()=>ctx.fiber.dispose());
  async function run(script,options){
    const adapter=new Adapter(script,options);ctx.llm.registerAdapter(['semantic-fixture'],adapter);
    const agent=await ctx.agentLoop.create('semantic-fixture',{provider:'semantic-fixture',model:'offline'},{cwd:workspace});
    const idle=new Promise(resolve=>{const dispose=ctx.on('agent/status',({agent:who,status})=>{if(who===agent&&status==='idle'){dispose();resolve();}});});
    agent.followup(createUserMessage({content:[{type:'text',text:'Implement public roundtrip behavior; inspect task.txt and source first.'}],source:{kind:'user'}}));
    await idle;
    const files=await readdir(auditDir);
    const state=JSON.parse(await readFile(path.join(auditDir,files.find(n=>n.endsWith('.json'))),'utf8'));
    const events=(await Promise.all(files.filter(n=>n.endsWith('.jsonl')).map(n=>readFile(path.join(auditDir,n),'utf8')))).flatMap(s=>s.trim().split('\n').filter(Boolean).map(JSON.parse));
    return{adapter,state,events,executed};
  }
  return{run,ctx};
}

function latestPanel(options){
  const texts=options.messages.flatMap(m=>(m.content??[]).filter(b=>b.type==='text').map(b=>b.text));
  const fresh=texts.filter(s=>s.startsWith('Updated KZ task state after pre-step review.')).at(-1);
  assert.ok(fresh,'pre-step route must be delivered on the next Solver request');
  return JSON.parse(fresh.slice(fresh.indexOf('\n')+1));
}

test('actual DSH loop: reconnaissance -> planner -> multi-step Solver -> loop -> preplanned new route', {timeout:20000},async t=>{
  const h=await host(t);
  const script=[...scout,options=>{assert.equal(latestPanel(options).semantic_planner.active_route.id,'D1');return action('python fail.py');},
    action('python fail.py'),action('python fail.py'),action('python fail.py'),
    options=>{assert.equal(latestPanel(options).semantic_planner.active_route.id,'D2');return action('python roundtrip.py');},'Partial offline fixture delivered.'];
  const {adapter,state,events,executed}=await h.run(script);
  assert.deepEqual(executed,['pwd','ls','cat task.txt','python fail.py','python roundtrip.py']);
  assert.equal(adapter.roles.filter(r=>r.role==='semantic_planner').length,2);
  assert.equal(state.full.semanticPlanner.active,'D2');assert.equal(state.full.semanticPlanner.switches,1);
  assert.equal(state.full.usage.roles.semantic_planner,2);assert.equal(state.full.usage.requests,adapter.requests.length);
  assert.equal(state.full.semanticPlanner.routes[0].executions,1);assert.equal(state.full.semanticPlanner.routes[1].executions,1);
  assert.ok(events.some(e=>e.event==='semantic_route_switched'&&e.to==='D2'));
  assert.ok(events.some(e=>e.event==='semantic_route_observation'&&e.route_id==='D2'));
  assert.equal(events.filter(e=>e.event==='semantic_plan_failed').length,0);
});

test('actual DSH loop: early implementation is gated without counting a failed execution', {timeout:15000},async t=>{
  const h=await host(t);const {state,executed,events}=await h.run([action('python repair.py'),...scout,action('python verify.py'),'Done fixture.']);
  assert.ok(!executed.includes('python repair.py'));assert.equal(state.full.semanticPlanner.reconnaissance.length,3);
  assert.equal(state.full.semanticPlanner.calls,1);assert.equal(state.full.recoveryClock.rejections,1);
  assert.equal(state.state.memories.filter(r=>r.outcome==='execution_failed').length,0);
  assert.ok(events.some(e=>e.event==='semantic_prelude_gate'));
});

test('actual DSH loop: premature delivery is steered into reconnaissance and planning', {timeout:15000},async t=>{
  const h=await host(t);const {state,events}=await h.run(['I should inspect the task.',...scout,action('python verify.py'),'Partial fixture.']);
  assert.equal(state.full.semanticPlanner.phase,'solving');assert.equal(state.full.semanticPlanner.calls,1);
  assert.equal(events.filter(e=>e.event==='semantic_prelude_requested').length,1);
});

test('actual DSH loop: malformed planner degrades and retries only after cooldown, with shared accounting', {timeout:15000},async t=>{
  const h=await host(t);const {state,adapter,executed,events}=await h.run([...scout,action('python repair.py'),action('python verify.py'),'Partial fixture.'],{badPlanner:true});
  assert.equal(state.full.semanticPlanner.phase,'degraded');assert.equal(state.full.semanticPlanner.calls,1);
  assert.equal(adapter.roles.filter(r=>r.role==='semantic_planner').length,1);
  assert.ok(executed.includes('python repair.py'));assert.equal(state.full.usage.requests,adapter.requests.length);
  assert.ok(events.some(e=>e.event==='semantic_plan_failed'));
});

test('actual DSH loop: last shared request remains available to Solver when planning cannot fit', {timeout:15000},async t=>{
  const h=await host(t,{maxRequests:4});const {state,adapter}=await h.run([...scout,'Partial: budget exhausted.']);
  assert.equal(adapter.requests.length,4);assert.equal(state.full.usage.requests,4);
  assert.equal(state.full.semanticPlanner.calls,0);assert.equal(state.full.semanticPlanner.phase,'degraded');
  assert.equal(state.full.semanticPlanner.lastError,'shared_budget_reserve_solver');
});

test('actual DSH loop: Monitor stagnation routes into Planner with current route evidence', {timeout:15000},async t=>{
  const h=await host(t,{monitorEnabled:true,monitorCooldown:5,semanticPlannerCooldown:1});
  const {state,adapter,events}=await h.run([...scout,action('python fail-a.py'),action('python fail-b.py'),action('python roundtrip.py'),'Partial fixture.']);
  assert.equal(state.full.semanticPlanner.active,'D2');
  const review=adapter.roles.find(r=>r.role==='semantic_planner'&&r.payload.stage==='route_review');
  assert.equal(review.payload.trigger.kind,'monitor_stalled');
  assert.deepEqual(review.payload.trigger.evidence_ids,['E4','E5']);
  assert.equal(events.filter(e=>e.event==='semantic_plan_failed').length,0);
});

test('deliverable config actually enables semantic mode inside plugin config',async()=>{
  const template=await readFile(new URL('../config/kz.patch.yml',import.meta.url),'utf8');
  // Ignore the application-specific !!js tags; this check is structural only.
  const yaml=renderConfig(template,'/opt/semantic/src/plugin.mjs').replace(/!!js /gu,'');
  const pluginConfig=parse(yaml)[0].insert[0].config;
  assert.equal(pluginConfig.semanticPlannerEnabled,true);assert.equal(pluginConfig.semanticReconnaissanceSteps,3);
  assert.equal(pluginConfig.semanticMaxRoutes,12);assert.equal(pluginConfig.criticEnabled,true);
});

test('actual DSH loop: every wake expands and evaluates a renewable bounded window', {timeout:20000},async t=>{
  const h=await host(t,{semanticMaxRoutes:2,semanticRouteWindow:1,semanticPlannerCooldown:1});
  const {state,adapter,events}=await h.run([...scout,action('python probe-a.py'),action('python probe-b.py'),action('python probe-c.py'),'Partial fixture.']);
  const calls=adapter.roles.filter(r=>r.role==='semantic_planner');
  assert.equal(calls.length,4);assert.deepEqual(calls.map(r=>r.payload.next_route_id),['D1','D3','D4','D5']);
  assert.ok(calls.every(r=>r.payload.routes.length<=2));
  assert.equal(state.full.semanticPlanner.totalGenerated,5);assert.equal(state.full.semanticPlanner.routes.length,2);
  assert.equal(state.full.semanticPlanner.evicted,3);assert.equal(state.full.semanticPlanner.totalVisited,3);
  assert.equal(state.full.semanticPlanner.active,'D5');
  const decisions=events.filter(e=>['semantic_route_selected','semantic_route_switched'].includes(e.event)&&e.source==='planner');
  assert.deepEqual(decisions.map(e=>e.proposed_ids.length),[2,1,1,1]);
  assert.deepEqual(decisions.map(e=>e.evaluations.length),[2,3,3,3]);
  assert.equal(events.filter(e=>e.event==='semantic_plan_failed').length,0);
});
