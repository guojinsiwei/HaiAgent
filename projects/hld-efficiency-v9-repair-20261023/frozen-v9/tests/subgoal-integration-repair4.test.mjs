import test from 'node:test';
import {fixtureReview} from './review-fixture.mjs';
import assert from 'node:assert/strict';
import { mkdir,mkdtemp,writeFile,readFile,readdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { createHash } from 'node:crypto';
import { Context } from '@deepseek-ai/cordis';
import LlmRuntime,{LlmAdapter,createUserMessage} from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import SessionStore,{Session} from '@deepseek-ai/dsh-session';
import SessionProjections from '@deepseek-ai/dsh-session-projection';
import AgentRegistry from '@deepseek-ai/dsh-agent';
import AgentLoop from '@deepseek-ai/dsh-agent-loop';
import {createScope} from '@deepseek-ai/dsh-scope';
import * as plugin from '../src/plugin.mjs';

const executeFile=promisify(execFile),args={command:'node check.cjs public'};
const publicTask='Complete HW3 and HW5. Preserve the public API and pass check.cjs.';
async function host(t,{realLoop=false,canonical=false}={}) {
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const dir=await mkdtemp(path.join(base,'subgoal-integration-r4-')),root=path.join(dir,'task'),auditDir=path.join(dir,'audit');await mkdir(root);
  await writeFile(path.join(root,'main.py'),'source');await writeFile(path.join(root,'task.md'),publicTask);
  await writeFile(path.join(root,'check.cjs'),"process.stdout.write('31/31 public checks passed\\n');");
  const ctx=new Context();await ctx.plugin(LlmRuntime);
  if(realLoop){await ctx.plugin(SessionStore);await ctx.plugin(SessionProjections);await ctx.plugin(AgentRegistry);}
  await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(plugin,{workspace:root,auditDir,full:true,maxRequests:30,maxTools:100,monitorCooldown:1,...(canonical?{taskInstructionPath:'task.md'}:{})});
  if(realLoop)await ctx.plugin(AgentLoop,{agents:[],maxParallelToolCalls:1});
  let executions=0;
  // Real child execution behind the actual DSH ToolRuntime; this deliberately
  // does not claim to test platform Bash or the production shell plugin.
  ctx.tools.register({name:'bash',description:'Offline public-check child process',parameters:{type:'object',additionalProperties:true},isConcurrencySafe:()=>false,
    output:{schema:{type:'object'},render:(_args,value)=>[{type:'text',text:value.stdout.text}]},
    async execute(value) {
      assert.match(value.command,/^node check\.cjs [a-z]+$/u);executions++;
      const output=await executeFile(process.execPath,['check.cjs',value.command.split(' ').at(-1)],{cwd:root});
      return {kind:'foreground',exitCode:0,timedOut:false,aborted:false,stopped:false,signal:null,stdout:{text:output.stdout,truncated:false},stderr:{text:output.stderr,truncated:false}};
    }});
  const session=Session.create('subgoal-integration-r4'),agent={id:session.id,session,ctx:createScope(ctx,{}).ctx};let calls=0;
  const execute=(name,arguments_)=>ctx.tools.execute({name,arguments:arguments_,callId:`r4-${++calls}`,agent,signal:new AbortController().signal});
  const state=async()=>{const files=await readdir(auditDir);return JSON.parse(await readFile(path.join(auditDir,files.find(x=>x.endsWith('.json'))),'utf8'));};
  t.after(()=>ctx.fiber.dispose());return {ctx,root,execute,state,executions:()=>executions};
}
const plan = targets => ({subgoal_plan:[{id:'G1',title:'public implementation',acceptance:'31 public checks pass',depends_on:[],targets}]});
const update = {id:'G1',reason:'actual public verification was discovered',expected_revision:1,verification:{arguments:args,stdout_contains:['31/31 public checks passed']}};
const binding = (revision=2,evidence_id='E1') => ({subgoal_id:'G1',revision,evidence_id});

test('R4 integration: real DSH metadata preserves an initial plan and binds a subsequently discovered public check',async t=>{
  const h=await host(t),absolute=path.join(h.root,'main.py');
  assert.equal((await h.execute('kz_update',plan([absolute]))).value.subgoals,'accepted');
  let state=await h.state();assert.equal(state.full.subgoals.items.G1.definition.targets[0],'main.py');assert.equal(state.full.subgoals.items.G1.status,'pending');
  assert.equal((await h.execute('bash',args)).isError,false);state=await h.state();
  assert.equal(h.executions(),1);assert.equal(state.full.evidence.E1.complete,true);assert.equal(state.full.evidence.E1.clean,true);
  assert.equal(state.full.subgoals.items.G1.checks,0);
  const response=await h.execute('kz_update',{subgoal_update:{...update,targets:[absolute]},verification_evidence:binding()});
  assert.equal(response.isError,false);assert.equal(response.value.subgoals,'accepted');assert.equal(response.value.verification.passed,true);
  state=await h.state();assert.equal(state.full.subgoals.items.G1.status,'check_passed');assert.equal(state.full.subgoals.items.G1.proof.evidence,'E1');assert.equal(state.full.subgoals.items.G1.revision,2);
});

test('R4 integration: unknown evidence and stale revisions stay recoverable and cannot create proof',async t=>{
  const h=await host(t);await h.execute('kz_update',plan(['main.py']));await h.execute('bash',args);
  await h.execute('kz_update',{subgoal_update:update});
  const missing=await h.execute('kz_update',{verification_evidence:binding(2,'E999')});
  assert.equal(missing.isError,false);assert.match(missing.value.verification.ignored,/complete actual/);
  const stale=await h.execute('kz_update',{verification_evidence:binding(1)});
  assert.equal(stale.isError,false);assert.match(stale.value.verification.ignored,/current revision/);
  assert.equal((await h.state()).full.subgoals.items.G1.proof,null);
  assert.equal((await h.execute('kz_update',{verification_evidence:binding()})).value.verification.passed,true);
});

test('R4 integration: fresh metadata fingerprints prevent an old successful check certifying edited source',async t=>{
  const h=await host(t);await h.execute('kz_update',plan(['main.py']));await h.execute('bash',args);
  await writeFile(path.join(h.root,'main.py'),'new source not covered by prior check');
  const result=await h.execute('kz_update',{subgoal_update:update,verification_evidence:binding()});
  assert.equal(result.value.verification.passed,false);assert.equal(result.value.verification.stableTargets,false);
  assert.equal((await h.state()).full.subgoals.items.G1.proof,null);assert.equal(h.executions(),1);
});

test('R4 integration: metadata cannot normalize an outside-workspace target into a valid goal',async t=>{
  const h=await host(t),response=await h.execute('kz_update',plan([path.join(path.dirname(h.root),'outside.py')]));
  assert.equal(response.isError,false);assert.ok(response.value.target_warnings.length);
  const goal=(await h.state()).full.subgoals.items.G1;
  assert.deepEqual(goal.definition.targets,[]);assert.equal(goal.definition.verification,undefined);assert.equal(goal.status,'pending');
});

class CanonicalAdapter extends LlmAdapter {
  requests=[];roles=[];solver=0;
  async resolveModel(provider,model){return {provider,id:model,name:model};}
  async *stream(options) {
    this.requests.push(options);let block;
    if(options.system) {
      const payload=JSON.parse(options.messages[0].content[0].text);let value;
      if(payload.question) {
        this.roles.push({role:'advisor',payload});
        value={alternatives:[{hypothesis:'Use public checks',check:'node check.cjs public',difference:'verify public task',evidence_ids:['E1']}]};
      } else if(payload.stage==='plan_checks') {
        this.roles.push({role:'critic',payload});
        value={decision:'accept',requirements:['HW3 and HW5'],gaps:[],checks:[{arguments:{command:'node check.cjs critic'},stdout_contains:['31/31 public checks passed']}]};
      } else if(payload.stage==='verdict') {
        this.roles.push({role:'critic',payload});value={decision:'accept',requirements:['HW3 and HW5'],gaps:[],checks:[]};
      } else {
        this.roles.push({role:'monitor',payload});const id=Object.values(payload.evidence).at(-1).id;
        value={verdict:'progress',reason:'public receipt available',evidence_ids:[id],memories:[]};
      }
      value=fixtureReview(payload,value);
      block={type:'text',text:JSON.stringify(value)};
    } else {
      const script=[{name:'bash',args:{command:'node check.cjs first'}},{name:'bash',args:{command:'node check.cjs second'}},{name:'kz_consult',args:{question:'Which assignment requirements should be verified?'}},'Delivered verified public checks.'];
      const step=script[this.solver++];if(!step)throw new Error('unexpected solver turn');
      block=typeof step==='string'?{type:'text',text:step}:{type:'tool-call',id:`canonical-${this.solver}`,name:step.name,arguments:JSON.stringify(step.args)};
    }
    yield {type:'block-start',index:0,blockType:block.type};
    if(block.type==='text')yield{type:'text-delta',index:0,text:block.text};else yield{type:'tool-call-delta',index:0,id:block.id,name:block.name,argumentsDelta:block.arguments};
    yield{type:'block-end',index:0,block};yield{type:'usage',usage:{inputTokens:10,outputTokens:5}};yield{type:'finish',reason:{kind:block.type==='text'?'stop':'tool-calls'}};
  }
}
test('R4 integration: official AgentLoop distributes the frozen canonical task to Solver, Monitor, Advisor and Critic', {timeout:15000},async t=>{
  const h=await host(t,{realLoop:true,canonical:true}),adapter=new CanonicalAdapter();h.ctx.llm.registerAdapter(['canonical-fixture'],adapter);
  const agent=await h.ctx.agentLoop.create('canonical-task',{provider:'canonical-fixture',model:'fixture'},{cwd:h.root});
  const idle=new Promise(resolve=>{const dispose=h.ctx.on('agent/status',({agent:who,status})=>{if(who===agent&&status==='idle'){dispose();resolve();}});});
  agent.followup(createUserMessage({content:[{type:'text',text:'Generated wrapper: complete HW4 and HW5.'}],source:{kind:'user'}}));await idle;
  const state=await h.state();assert.equal(state.full.taskGoal,publicTask);assert.match(state.full.wrapperTaskGoal,/HW4/);
  assert.equal(state.full.taskInstruction.sha256,createHash('sha256').update(publicTask).digest('hex'));
  const solver=adapter.requests.filter(request=>!request.system);assert.equal(solver.length,4);
  assert.ok(JSON.stringify(solver[0]).includes(publicTask));
  for(const role of ['monitor','advisor','critic']) {
    const rows=adapter.roles.filter(row=>row.role===role);assert.ok(rows.length,`missing ${role} invocation`);
    for(const {payload} of rows)assert.equal(payload.task??payload.original_task,publicTask,`${role} must use canonical task rather than wrapper`);
  }
  assert.equal(state.full.critic.decision,'public_review_accepted');assert.equal(h.executions(),3);
});
