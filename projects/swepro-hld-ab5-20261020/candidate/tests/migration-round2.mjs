// Independent migration acceptance contracts. Failing assertions are findings,
// not changes to runtime behavior or permission to run a paid experiment.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Context} from '@deepseek-ai/cordis';
import LlmRuntime from '@deepseek-ai/dsh-llm';
import ToolRuntime from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import {Session} from '@deepseek-ai/dsh-session';
import {createScope,scopeOf} from '@deepseek-ai/dsh-scope';
import * as plugin from '../src/plugin.mjs';
import {FullTask} from '../src/full-task.mjs';
import {Policy} from '../src/policy.mjs';
const S='sha256:fixed',deps={'main.py':'file:a'};
const call=command=>({name:'bash',arguments:{command}});
const failure={executed:true,complete:true,exitCode:1,stdout:'',stderr:'SyntaxError: invalid syntax'};
const ordinary={...failure,stderr:'assertion failed'};
const candidate={kind:'blocker',conclusion:'Known main.py compile failure',condition:'same source',operation:'compile',targets:['main.py'],evidence_ids:['E1']};

test('R2-01 exhausted local correction must return subsequent defects to normal failure accounting',()=>{
  const f=new FullTask({}),p=new Policy();
  for(let i=0;i<4;i++) {
    const c=call(`python broken${i}.py`);assert.equal(f.before(c,p,S).allowed,true);
    f.observe(c,failure,S,S,{},{},p,'raw');
  }
  assert.ok(p.anchors().length>0,'four executed syntax failures still yield zero exploration anchors');
  assert.equal(f.state.local,null,'exhausted correction episode should end');
});

test('R2-02 disabling local correction must not silently discard execution defects',()=>{
  const f=new FullTask({localCorrection:false}),p=new Policy();
  f.observe(call('python broken.py'),failure,S,S,{},{},p,'raw');
  assert.equal(p.anchors().length,1,'disabled correction still suppresses the failure anchor');
});

test('R2-03 operation plus unchanged target must urgently surface a blocker missed by keyword recall',()=>{
  const f=new FullTask({}),p=new Policy();
  f.state.evidence.E1={id:'E1',complete:true,after:S,stdout:'compile failed',stderr:'',dependenciesAfter:deps};
  const m=f.memory.admit(candidate,f.state.evidence,['E1'],S,deps);
  f.state.scope=S;f.state.dependencies=deps;f.state.visibleMemories=[];
  const decision=f.before(call('python compile main.py --diagnostic'),p,S,deps);
  assert.equal(decision.allowed,false,'target/operation blocker is not surfaced without exact commandKey');
  assert.ok(f.state.urgent.includes(m.id));
});

test('R2-04 unrelated newer evidence is not sufficient justification for an identical failed retry',()=>{
  const f=new FullTask({}),p=new Policy(),c=call('python main.py');
  c.commandDependencies=deps;
  f.observe(c,ordinary,S,S,deps,deps,p,'raw1');
  f.observe(call('cat unrelated.txt'),{...ordinary,exitCode:0,stderr:'',stdout:'unrelated notes'},S,S,deps,deps,p,'raw2');
  const m=f.memory.admit(candidate,f.state.evidence,['E1'],S,deps);f.state.visibleMemories=[m.id];
  const proposal={tool:'bash',arguments:c.arguments,evidence_ids:['E2'],strategy_adjustment:'Retry based on the new note',
    memory_review:{ids:[m.id],observed_result:'assertion failed',applicability:'same source',reason:'a new note exists',decision:'justified_retry',new_evidence:'read unrelated notes'}};
  f.reviewProposal(proposal);assert.equal(p.propose(proposal,{visibleEvidence:['E1','E2']}).accepted,true);
  const decision=f.before(c,p,S,deps);
  assert.equal(decision.allowed,false,'an unrelated read unlocked a discriminating retry: '+JSON.stringify(decision));
});

test('R2-05 real DSH native write should not bypass the required visible-memory decision review',async t=>{
  const base=fileURLToPath(new URL('../.runtime/',import.meta.url));await mkdir(base,{recursive:true});
  const dir=await mkdtemp(path.join(base,'round2-')),workspace=path.join(dir,'task');await mkdir(workspace);await writeFile(path.join(workspace,'main.py'),'original');
  const ctx=new Context();await ctx.plugin(LlmRuntime);await ctx.plugin(SystemPrompt,{});await ctx.plugin(ToolRuntime,{mode:'native'});
  await ctx.plugin(plugin,{workspace,auditDir:path.join(dir,'audit'),full:true});t.after(()=>ctx.fiber.dispose());
  ctx.tools.register({name:'bash',description:'offline failing check',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'compile failed'}]},execute:()=>({kind:'foreground',exitCode:1,stdout:{text:'',truncated:false},stderr:{text:'compile failed',truncated:false}})});
  let writes=0;
  ctx.tools.register({name:'write',description:'offline native write fixture',parameters:{type:'object'},output:{schema:{type:'object'},render:()=>[{type:'text',text:'written'}]},execute:async args=>{writes++;await writeFile(path.join(workspace,'main.py'),args.content);return {written:true};}});
  const agent={session:Session.create('round2'),ctx:createScope(ctx,{}).ctx};agent.id=agent.session.id;let seq=0;
  const execute=(name,args)=>ctx.tools.execute({name,arguments:args,callId:`r2-${++seq}`,agent,signal:new AbortController().signal});
  await execute('bash',{command:'python main.py'});await ctx.systemPrompt.assemble({scope:scopeOf(agent.ctx)});
  const admitted=await execute('kz_update',{memory:candidate});assert.equal(admitted.value.memory.id,'M1');
  const prompt=await ctx.systemPrompt.assemble({scope:scopeOf(agent.ctx)});assert.match(JSON.stringify(prompt),/M1/);
  await execute('write',{file_path:path.join(workspace,'main.py'),content:'replacement without memory review'});
  assert.equal(writes,0,'native write executed despite no kz_strategy/memory review; bash has this guard');
});

test('R2-06 positive: same-command blocker still forces recall, relevant source change permits retry',()=>{
  const f=new FullTask({}),p=new Policy(),c=call('python main.py');c.commandDependencies=deps;
  f.observe(c,ordinary,S,S,deps,deps,p,'raw1');f.observe(c,ordinary,S,S,deps,deps,p,'raw2');
  assert.equal(f.before(c,p,S,deps).allowed,false);assert.ok(f.state.urgent.length>0);
  const changed={'main.py':'file:b'};f.state.dependencies=changed;f.state.visibleMemories=[];
  assert.equal(f.before(c,p,'sha256:changed',changed).allowed,true);
});

test('R2-07 positive: subgoal check evidence invalidates after a source edit, without automatic rollback',()=>{
  const f=new FullTask({}),p=new Policy();
  f.metadata({subgoal_plan:[{id:'G1',title:'implement',acceptance:'public checks',targets:['main.py'],depends_on:[],verification:{arguments:{command:'python test_main.py'},stdout_contains:['passed']}}]});
  f.observe(call('python test_main.py'),{...ordinary,exitCode:0,stdout:'passed',stderr:''},S,S,deps,deps,p,'raw');
  assert.equal(f.goals.state.items.G1.status,'check_passed');
  f.goals.sync({'main.py':'file:b'});assert.equal(f.goals.state.items.G1.status,'needs_recheck');
  assert.equal(f.state.pendingRollback,null);assert.deepEqual(f.state.checkpoints,[]);
});
