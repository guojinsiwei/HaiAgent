import test from 'node:test';
import assert from 'node:assert/strict';
import {contextDelta,criticView,roleOutputLimit,deferPeriodicPlanner,periodicPlannerWaiting,efficientReviewGuard,countEfficientReview} from '../src/efficiency.mjs';
import {askRole} from '../src/roles.mjs';
import {configuration} from '../src/policy.mjs';
import {assessProgress} from '../src/mechanism-evidence.mjs';

function apply(before,text) {
  const patch=JSON.parse(text);if(patch.mode==='replace')return patch.value;
  const result=structuredClone(before);
  for(const op of patch.operations) {
    const parent=op.path.slice(0,-1).reduce((o,k)=>o[k],result),key=op.path.at(-1);
    if(op.op==='remove')delete parent[key];else parent[key]=op.value;
  }
  return result;
}
test('same-step patches reconstruct exact context including removals, evidence and memory changes',()=>{
  const before={task:'x'.repeat(12000),monitor:{verdict:'uncertain'},advice:null,memories:[],completion:{gaps:['old'],status:'open'},evidence:[{id:'E1',stdout:'old'}],old_field:true};
  const after={...before,monitor:{verdict:'stalled'},advice:{hypothesis:'inspect input types'},memories:[{id:'M1',status:'disputed'}],completion:{gaps:[],status:'pending'},evidence:[{id:'E2',stdout:'current'}]};
  delete after.old_field;
  const patch=contextDelta(before,after);
  assert.deepEqual(apply(before,patch),after);
  assert.ok(patch.length<JSON.stringify(after).length/5);
  assert.equal(contextDelta(after,structuredClone(after)),null);
  assert.equal(before.completion.gaps.length,1);
});
test('patch uses full replacement when it is smaller and preserves hostile literal strings',()=>{
  const before={a:'x'},after={a:'{{not_a_variable}}',b:{'a/b':'raw <script>'}};
  const delta=contextDelta(before,after);
  assert.equal(JSON.parse(delta).mode,'replace');assert.deepEqual(apply(before,delta),after);
});
test('receipt projection leaves complete ledger untouched and retains unresolved review status',()=>{
  const critic={decision:'needs_revision',rounds:8,lastError:'missing independent expectation',receipts:Array.from({length:20},(_,i)=>({evidence_id:`E${i+1}`,passed:false,stdout:'x'.repeat(5000),gap_ids:['Gap-1']}))};
  const before=JSON.stringify(critic),view=criticView(critic);
  assert.equal(JSON.stringify(critic),before);assert.equal(view.receipt_count,20);
  assert.equal(view.decision,'needs_revision');assert.equal(view.receipts.length,2);
  assert.equal(view.full_ref,'kz_history id=context');assert.ok(JSON.stringify(view).length<before.length/10);
});

function progressFixture() {
  const row={id:'E1',key:'check',complete:true,executed:true,stdout:'count=3',stderr:'',semanticRoute:'D1'};
  const state={evidence:{E1:row}};
  const review={verdict:'progress',evidence_ids:['E1'],progress_claim:{requirement_ref:'Q1',kind:'requirement_check',predicate:'row count',expected_basis:'public contract',support:[{evidence_id:'E1',field:'stdout',quote:'count=3'}]}};
  assert.equal(assessProgress(review,state,[{id:'Q1'}],state.evidence).accepted,true);
  state.monitor={verdict:'progress',evidence_ids:['E1']};
  const active={id:'D1',executions:12,reviewed_at:0,evidence_ids_observed:['E1']};
  return {state,active,planner:{state:{pending:{kind:'route_window'}},active:()=>active},config:{semanticRouteWindow:12}};
}
test('periodic review defers once per attributed progress, cannot starve the hard backstop',()=>{
  const {state,planner,config,active}=progressFixture();
  assert.equal(deferPeriodicPlanner(state,planner,config),true);
  active.executions=23;assert.equal(periodicPlannerWaiting(state,planner,config),true);
  active.executions=24;assert.equal(periodicPlannerWaiting(state,planner,config),false);
  assert.equal(deferPeriodicPlanner(state,planner,config),false);
  state.progressClaims.last.predicate='next predicate';
  assert.equal(deferPeriodicPlanner(state,planner,config),true);
  active.executions=36;assert.equal(periodicPlannerWaiting(state,planner,config),false);
  state.progressClaims.last.predicate='third predicate';assert.equal(deferPeriodicPlanner(state,planner,config),false);
});
test('loop triggers, protocol failures, stale/foreign evidence and bare exit zero never defer planning',()=>{
  for(const kind of ['initial','rejection_loop','repeated_observation_loop','repeated_failure_family','monitor_stalled','completion_review_stalled','delivery_without_predicate_progress']) {
    const {state,planner,config}=progressFixture();deferPeriodicPlanner(state,planner,config);planner.state.pending.kind=kind;
    assert.equal(periodicPlannerWaiting(state,planner,config),false,kind);assert.equal(deferPeriodicPlanner(state,planner,config),false,kind);
  }
  for(const mutate of [f=>delete f.state.progressClaims,f=>f.state.monitor.verdict='uncertain',f=>f.state.monitor.evidence_ids=['E2'],f=>f.planner.state.protocolFailures=1,f=>f.state.evidence.E1.nativeToolError=true,f=>f.state.evidence.E1.semanticRoute='D2',f=>f.active.evidence_ids_observed=[]]) {
    const f=progressFixture();mutate(f);assert.equal(deferPeriodicPlanner(f.state,f.planner,f.config),false);
  }
});
test('review quotas survive scratch edits, closed gaps, restarts and changed deliverables',()=>{
  let state={delivery:{requested_artifacts:['out.c']},dependencies:{'out.c':'v1'},completion:{status:'pending',gaps:[{id:'Gap-1',status:'open'}]}};
  const admit=()=>{const a=efficientReviewGuard(state,null);assert.equal(a.allowed,true);countEfficientReview(state,a);};
  for(let i=0;i<3;i++){state.scope=`scratch${i}`;state.dependencies['test.py']=`v${i}`;admit();}
  assert.equal(efficientReviewGuard(state,null).allowed,false);
  state=JSON.parse(JSON.stringify(state));assert.equal(efficientReviewGuard(state,null).allowed,false);
  state.dependencies['out.c']='v2';for(let i=0;i<3;i++)admit();
  state.dependencies['out.c']='v3';assert.equal(efficientReviewGuard(state,null).terminal,true);
  assert.equal(state.completion.status,'pending');assert.equal(state.completion.gaps[0].status,'open');
});
test('application revision permits repairs; unknown file targets cannot replenish quotas',()=>{
  for(const world of [null,{revision:1,submitted:false}]) {
    const s={};for(let i=0;i<3;i++)countEfficientReview(s,efficientReviewGuard(s,world));
    assert.equal(efficientReviewGuard(s,world).allowed,false);
    if(world)assert.equal(efficientReviewGuard(s,{revision:2,submitted:false}).allowed,true);
    else {s.scope='changed';s.subgoals={items:{G1:{definition:{targets:['new.py']}}}};assert.equal(efficientReviewGuard(s,null).allowed,false);}
  }
});
test('role caps are contract-aware and bounded by the original route',()=>{
  const route={maxTokens:16384};
  assert.equal(roleOutputLimit('monitor',{},route,{}),2048);
  assert.equal(roleOutputLimit('semantic_planner',{},route,{}),4096);
  assert.equal(roleOutputLimit('critic',{stage:'verdict'},route,{}),6144);
  assert.equal(roleOutputLimit('critic',{requirement_catalog:Array(200)},route,{}),16384);
  assert.equal(roleOutputLimit('critic',{}, {maxTokens:1000},{}),1000);
  assert.equal(roleOutputLimit('monitor',{},route,{efficiency:{truncations:{monitor:2}}}),8192);
  assert.throws(()=>configuration({efficiencyEnabled:'true'}));assert.equal(configuration().efficiencyEnabled,false);
});
test('actual role request uses cap, never accepts a truncated response and expands only subsequent attempt',async()=>{
  const requests=[],events=[],sessions=new Map();let truncated=true;
  const ctx={llm:{async *stream(request){requests.push(request);yield {type:'block-end',block:{type:'text',text:'{"decision":"accept"}'}};yield{type:'finish',reason:{kind:truncated?'max-tokens':'stop'}};}}};
  const entry={id:'fixture',full:{config:{efficiencyEnabled:true},state:{roleSerial:0,route:{provider:'fixture',model:'fixture',maxTokens:16384}}}};
  const call=()=>askRole(ctx,entry,'monitor','rules',{},undefined,(_e,event,data)=>events.push({event,...data}),sessions);
  await assert.rejects(call(),/incomplete/);assert.equal(requests.length,1);assert.equal(requests[0].maxTokens,2048);assert.equal(sessions.size,0);
  truncated=false;await call();assert.equal(requests[1].maxTokens,4096);assert.equal(entry.full.state.route.maxTokens,16384);
  assert.ok(events.some(e=>e.event==='efficiency_role_truncated'));
});
