import test from 'node:test';
import assert from 'node:assert/strict';
import {FullTask} from '../src/full-task.mjs';
import {Policy,actionKey} from '../src/policy.mjs';
import {MemoryEffects} from '../src/memory-effects.mjs';
import {CriticCache} from '../src/critic-cache.mjs';
const S='sha256:a',deps={'main.py':'file:a'},args={command:'python main.py'};
const c={name:'bash',arguments:args,callId:'bash-1',commandDependencies:deps};
const failed={executed:true,complete:true,exitCode:1,stdout:'',stderr:'assertion failed'};
const candidate={kind:'blocker',conclusion:'compile failed',condition:'same source',operation:'compile',targets:['main.py'],evidence_ids:['E1']};
function setup() {
  const f=new FullTask({}),p=new Policy();f.observe(c,failed,S,S,deps,deps,p,'raw');
  const m=f.memory.admit(candidate,f.state.evidence,['E1'],S,deps);f.state.visibleMemories=[m.id];
  return {f,p,m};
}
function proposal(tool,arguments_) {return {tool,arguments:arguments_,evidence_ids:['E1'],strategy_adjustment:'repair the observed implementation',memory_review:{ids:['M1'],decision:'apply',observed_result:'failed',applicability:'same source',reason:'correct relevant source'}};}

test('repair2 native review is exact-tool/exact-arguments and one-shot, without orthogonality proof',()=>{
  const {f,p}=setup(),a={file_path:'main.py',content:'fixed'};p.state.active=true;
  assert.equal(p.propose(proposal('write',a),{visibleEvidence:['E1']}).accepted,true);
  assert.equal(f.before({name:'write',arguments:a,callId:'write-1'},p,S,deps).allowed,true);
  assert.equal(f.before({name:'write',arguments:a,callId:'write-2'},p,S,deps).allowed,true);
  p.propose(proposal('write',a),{visibleEvidence:['E1']});
  assert.equal(f.before({name:'edit',arguments:a},p,S,deps).allowed,true);
  p.propose(proposal('write',a),{visibleEvidence:['E1']});
  assert.equal(f.before({name:'write',arguments:{...a,content:'different'}},p,S,deps).allowed,true);
});

test('native edits remain available with memories and create no form rejections',()=>{
  const empty=new FullTask({}),p0=new Policy(),call={name:'edit',arguments:{file_path:'main.py'},callId:'edit'};
  assert.equal(empty.before(call,p0,S,deps).allowed,true);
  const {f,p}=setup();for(let i=0;i<7;i++)assert.equal(f.before(call,p,S,deps).allowed,true);
  assert.equal(p.state.counters.denied,0);assert.equal(p.state.advisory,false);
});

test('repair2 operation matching does not revive stale or target-mismatched blockers',()=>{
  const {f}=setup(),call={name:'bash',arguments:{command:'python compile main.py'}};
  assert.equal(f.memory.matchAction(call,S,deps).length,1);
  assert.equal(f.memory.matchAction(call,S,{'main.py':'file:b'}).length,0);
  assert.equal(f.memory.matchAction({name:'bash',arguments:{command:'python compile other.py'}},S,deps).length,0);
  assert.equal(f.memory.matchAction({name:'write',arguments:{}},S,deps,['main.py']).length,1);
});

test('repair2 complete quoted related observation permits one hypothesis retry, never repeated same-result retries',()=>{
  const {f,p}=setup();
  f.observe({...c,callId:'read-1',arguments:{command:'cat main.py'}},{...failed,exitCode:0,stderr:'',stdout:'SPECIAL_CASE = 2'},S,S,deps,deps,p,'raw2');
  const next=proposal('bash',args);next.evidence_ids=['E2'];Object.assign(next.memory_review,{decision:'justified_retry',new_evidence:'special case read',hypothesis:'failure may depend on special case',support:[{evidence_id:'E2',target:'main.py',field:'stdout',quote:'SPECIAL_CASE = 2'}]});
  p.propose(next,{visibleEvidence:['E1','E2']});assert.equal(f.before(c,p,S,deps).reason,'one_evidence_linked_discriminating_retry');
  f.observe(c,failed,S,S,deps,deps,p,'raw3');
  p.propose(next,{visibleEvidence:['E1','E2','E3']});assert.equal(f.before(c,p,S,deps).allowed,false);
});

for(const issue of ['unrelated_target','fake_quote','old_evidence','incomplete','tracked_not_observed','no_hypothesis'])test(`repair2 retry rejects ${issue}`,()=>{
  const {f,p}=setup();f.observe({...c,arguments:{command:'cat main.py'}},{...failed,exitCode:0,stderr:'',stdout:'new observation'},S,S,deps,deps,p,'raw2');
  const next=proposal('bash',args);next.evidence_ids=['E2'];Object.assign(next.memory_review,{decision:'justified_retry',new_evidence:'fresh',hypothesis:'specific related hypothesis',support:[{evidence_id:'E2',target:'main.py',field:'stdout',quote:'new observation'}]});
  const q=next.memory_review.support[0];
  if(issue==='unrelated_target')q.target='unrelated.txt';
  if(issue==='fake_quote')q.quote='invented';
  if(issue==='old_evidence'){q.evidence_id='E1';next.evidence_ids=['E1'];}
  if(issue==='incomplete')f.state.evidence.E2.complete=false;
  if(issue==='tracked_not_observed')f.state.evidence.E2.observedTargets=['unrelated.txt'];
  if(issue==='no_hypothesis')delete next.memory_review.hypothesis;
  p.propose(next,{visibleEvidence:['E1','E2']});assert.equal(f.before(c,p,S,deps).allowed,false);
});

test('repair2 actual related edit needs no extra retry-support schema',()=>{
  const {f,p}=setup(),changed={'main.py':'file:b'};f.state.dependencies=changed;
  p.propose(proposal('bash',args),{visibleEvidence:['E1']});
  assert.equal(f.before(c,p,'sha256:changed',changed).allowed,true);
});

test('optional memory review-to-result survives snapshot without a fabricated intervention',()=>{
  let {f,p}=setup();const a={file_path:'main.py',content:'fixed'},call={name:'write',arguments:a,callId:'w'};
  assert.equal(f.before(call,p,S,deps).allowed,true);
  f=new FullTask({},JSON.parse(JSON.stringify(f.snapshot())));
  p.propose(proposal('write',a),{visibleEvidence:['E1']});assert.equal(f.before(call,p,S,deps).allowed,true);
  const row=f.observeNative(call,{complete:true,stdout:'written',stderr:'',exitCode:null},S,'sha256:b',deps,{'main.py':'file:b'},'raw2');
  const events=f.effects.drain(),out=events.find(x=>x.event==='memory_followup_outcome');
  assert.equal(out.callId,'w');assert.equal(out.evidence_id,row.id);assert.equal(out.intervention_id,null);
  assert.deepEqual(out.memory_ids,['M1']);assert.equal(out.workspace_changed,true);assert.equal(out.clean_check,false);assert.equal(out.causal_benefit_proven,false);
});

test('repair2 memory receipts bind by call ID under out-of-order completion; unknown execution is not success',()=>{
  const m=new MemoryEffects(),a={...c,callId:'a'},b={...c,callId:'b',arguments:{command:'python other.py'}};
  m.intervene(a,['M1'],S);m.bind(a,{ids:['M1'],decision:'apply'},S);m.bind(b,{ids:['M2'],decision:'recheck'},S);
  m.finish('b',{id:'E2',complete:true,clean:true,before:S,after:S,exitCode:0});m.finish('a',null);
  const results=m.drain().filter(x=>x.event==='memory_followup_outcome');assert.deepEqual(results.map(x=>x.memory_ids),[['M2'],['M1']]);
  assert.equal(results[1].observed,false);assert.equal(results[1].clean_check,false);
});

function cacheFixture() {
  const f=new FullTask({});f.state.scope=S;f.state.dependencies=deps;f.state.observed=1;
  f.goals.define({subgoal_plan:[{id:'G1',title:'test',acceptance:'public check',targets:['main.py'],depends_on:[],verification:{arguments:args,stdout_contains:['passed']}}]});
  const check={arguments:args,stdout_contains:['passed'],cache_scope:'workspace'};
  const row={id:'E1',complete:true,clean:true,before:S,after:S,stdout:'passed',stderr:'',exitCode:0,key:actionKey(c),dependenciesBefore:deps,dependenciesAfter:deps};
  return {f,check,row,cache:new CriticCache()};
}
test('repair2 Critic reuses only explicit unchanged workspace check receipt',()=>{
  const {f,check,row,cache}=cacheFixture();cache.put(check,f,row);assert.equal(cache.get(check,f).id,'E1');
  assert.equal(cache.get({...check,fresh:true},f),null);assert.equal(cache.get({...check,cache_scope:undefined},f),null);
  assert.equal(new CriticCache().get(check,f),null);
});
for(const issue of ['changed_scope','changed_dependency','unknown_scope','intervening_observation','failed_check','partial_check','mutating_check'])test(`repair2 Critic does not reuse ${issue}`,()=>{
  const {f,check,row,cache}=cacheFixture();
  if(issue==='failed_check')row.clean=false;
  if(issue==='partial_check')row.complete=false;
  if(issue==='mutating_check')row.before='sha256:other';
  cache.put(check,f,row);
  if(issue==='changed_scope')f.state.scope='sha256:b';
  if(issue==='changed_dependency')f.state.dependencies={'main.py':'file:b'};
  if(issue==='unknown_scope')f.state.scope='unknown';
  if(issue==='intervening_observation')f.state.observed++;
  assert.equal(cache.get(check,f),null);
});
