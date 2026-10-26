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
      if(p.stage==='plan_checks') {
        const quote='Implement public roundtrip behavior';
        answer=JSON.stringify({decision:'revise',requirements:[quote],gaps:['roundtrip unverified'],checks:[{arguments:{command:this.options.badCheck?'echo fake':'python verify.py',description:'public boundary check'},stdout_contains:['public files'],gap_refs:['roundtrip unverified'],gap_ids:[],requirement_quotes:[quote],provenance:{author:'critic',kind:'independent_derivation',expected_rule:'public roundtrip boundary',sources:[{kind:'task',quote}],independence:'assert original public behavior',derivation:'Check the public task roundtrip boundary with the available test'}}]});
        if(this.options.noChecks)answer=JSON.stringify({decision:'revise',reason_kind:'repair_implementation',requirements:[],gaps:p.existing_gaps.length?[]:['roundtrip implementation missing'],gap_updates:p.existing_gaps.map(g=>({gap_id:g.id,detail:'same missing implementation',status:'open'})),checks:[],next_step:'implement roundtrip before requesting review'});
      }else if(p.stage==='verdict'){
        const id=p.actual_check_observations[0].evidence_id,quote='Implement public roundtrip behavior';
        answer=JSON.stringify({decision:'accept',requirements:[quote],gaps:[],checks:[],requirement_evidence:[{requirement_quote:quote,evidence_ids:[id],reason:'public check covers roundtrip boundary'}],gap_updates:p.existing_gaps.map(g=>({gap_id:g.id,status:'closed',evidence_ids:[id],reason:'targeted public boundary assertion supplies expected-value basis'}))});
      }else if(['initial_plan','route_review'].includes(p.stage)){
        this.roles.push({role:'semantic_planner',payload:p});
        answer=this.options.badPlanner?'invalid JSON':JSON.stringify(p.stage==='initial_plan'?plan():switchPlan(p));
        if(this.options.v3){const a=JSON.parse(answer);answer=JSON.stringify({...a,new_routes:a.routes.map(r=>({...r,evaluation:a.evaluations.find(e=>e.route_id===r.id)})),existing_evaluations:Object.fromEntries(a.evaluations.filter(e=>p.routes.some(r=>r.id===e.route_id)).map(e=>[e.route_id,e])),memory_use:[]});}
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
    maxRequests:30,maxTools:50,advisorCooldownTools:5,semanticReconnaissanceSteps:3,...config});
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


for(const arm of ['hld'])test('actual DSH Critic registers, targets, verifies and closes a new gap in one round', {timeout:20000},async t=>{
  const h=await host(t,{semanticPlannerEnabled:false,criticEnabled:true});
  const {state,events,executed}=await h.run(['Ready for public review.']);
  assert.ok(executed.includes('python verify.py'));
  assert.ok(events.some(e=>e.event==='critic_review'&&e.accepted));
  const event=events.find(e=>e.event==='completion_review');assert.equal(event.completion.status,'completed_publicly');
  assert.equal(events.filter(e=>e.event==='critic_unavailable').length,0);
});

test('actual DSH invalid checker schema never creates a durable task gap', {timeout:20000},async t=>{
  const h=await host(t,{semanticPlannerEnabled:false,criticEnabled:true});
  const {events,executed}=await h.run(['Review me.','Cannot prepare the check.','Still incomplete.'],{badCheck:true});
  assert.equal(executed.length,0);
  assert.ok(events.some(e=>e.event==='critic_protocol_error'));
  assert.equal(events.filter(e=>e.event==='critic_plan_registered').length,0);
  assert.ok(!events.some(e=>e.event==='critic_review'&&e.accepted));
});

test('CLI completion loop hands control to semantic replanning and bounds paid review without accepting', {timeout:30000},async t=>{
  process.env.HLD_PLANNER_PROTOCOL='3';t.after(()=>{delete process.env.HLD_PLANNER_PROTOCOL;});
  const h=await host(t,{criticEnabled:true,semanticPlannerCooldown:1});
  const script=[...scout,...Array.from({length:12},(_,i)=>[action('cat observation'+i),'Please review.']).flat()];
  const {events,state,adapter}=await h.run(script,{noChecks:true,v3:true});
  assert.ok(events.some(e=>e.event==='completion_recovery_queued'));
  assert.ok(events.some(e=>e.event==='semantic_route_switched'&&e.trigger.kind==='completion_review_stalled'));
  assert.ok(events.filter(e=>e.event==='role_request'&&e.role==='critic').length<=3);
  assert.equal(state.full.completion.gaps.length,1);
  assert.ok(!events.some(e=>e.event==='critic_review'&&e.accepted));
  assert.ok(adapter.requests.length<30);
});
