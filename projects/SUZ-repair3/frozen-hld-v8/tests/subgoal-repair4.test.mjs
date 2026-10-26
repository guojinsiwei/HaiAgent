import test from 'node:test';
import assert from 'node:assert/strict';
import { Subgoals } from '../src/subgoals.mjs';
import { actionKey } from '../src/policy.mjs';

const deps = { 'main.py': 'file:source', 'other.py': 'file:other' };
const args = { command: 'python -m pytest tests/test_main.py' };
const verification = { arguments: args, stdout_contains: ['31 passed'] };
const goal = { id:'G1', title:'parser', acceptance:'public parser behavior passes', targets:['main.py'], depends_on:[], verification };
const make = () => { const g = new Subgoals(); g.define({subgoal_plan:[goal]}); return g; };
const row = (patch={}) => ({ id:'E1', tool:'bash', executed:true, complete:true, exitCode:0, clean:true, stdout:'31 passed', stderr:'', key:actionKey({name:'bash',arguments:args}), dependenciesBefore:deps, dependenciesAfter:deps, after:'sha256:state', ...patch });
const binding = (revision=1,evidence_id='E1') => ({subgoal_id:'G1',revision,evidence_id});

test('R4 subgoals: planning without a verification remains visible and cannot pass',()=>{
  const g = new Subgoals(); const { verification: omitted, ...planned } = goal;
  g.define({subgoal_plan:[planned],subgoal_id:'G1'});
  assert.equal(g.view().goals[0].verification_status,'awaiting_definition');
  assert.equal(g.view().suggested,'G1'); assert.deepEqual(g.observe(row()),[]);
  assert.throws(()=>g.bindVerification(binding(),{E1:row()},deps),/register/);
  g.define({subgoal_update:{id:'G1',reason:'public test command discovered',expected_revision:1,verification}});
  assert.equal(g.state.items.G1.revision,2);
  assert.equal(g.bindVerification(binding(2),{E1:row()},deps).passed,true);
});

test('R4 subgoals: an explicit revised command binds actual test evidence, not semantic similarity',()=>{
  const g = make(), newArgs = {command:'python tests/check_parser.py --all'};
  const actual = row({stdout:'12/12 checks passed',key:actionKey({name:'bash',arguments:newArgs})});
  assert.throws(()=>g.bindVerification(binding(),{E1:actual},deps),/does not match/);
  g.define({subgoal_update:{id:'G1',reason:'repository provides a different public check',expected_revision:1,verification:{arguments:newArgs,stdout_contains:['12/12 checks passed']}}});
  assert.throws(()=>g.bindVerification(binding(),{E1:actual},deps),/current revision/);
  assert.equal(g.bindVerification(binding(2),{E1:actual},deps).passed,true);
  assert.equal(g.state.items.G1.proof.revision,2); assert.equal(g.state.items.G1.lastEvidence,'E1');
});

test('R4 subgoals: revision invalidates old and dependent proofs while preserving audit history',()=>{
  const g = make(); g.define({subgoal_plan:[{...goal,id:'G2',depends_on:['G1']}]});
  g.observe(row()); assert.equal(g.state.items.G1.status,'check_passed'); assert.equal(g.state.items.G2.status,'check_passed');
  g.define({subgoal_update:{id:'G1',reason:'cover additional public behavior',acceptance:'additional edge cases must pass'}});
  assert.equal(g.state.items.G1.revision,2); assert.equal(g.state.items.G1.proof,null);
  assert.equal(g.state.items.G1.history[0].proof.evidence,'E1');
  assert.equal(g.state.items.G2.status,'needs_recheck'); assert.equal(g.state.items.G2.proof,null);
});

test('R4 subgoals: plan cannot silently rewrite definitions and stale updates stay atomic',()=>{
  const g=make(),before=structuredClone(g.state);
  assert.throws(()=>g.define({subgoal_plan:[{...goal,title:'changed'}]}),/immutable/);
  assert.throws(()=>g.define({subgoal_update:{id:'G1',reason:'old view',expected_revision:0,title:'changed'}}),/stale/);
  assert.deepEqual(g.state,before);
  assert.throws(()=>g.define({subgoal_update:{id:'G1',reason:'claimed success',status:'check_passed'}}),/may not mark/);
  assert.deepEqual(g.state,before);
});

test('R4 subgoals: updated dependency cycles and invalid targets cannot partially change a goal',()=>{
  const g=make(),before=structuredClone(g.state);
  assert.throws(()=>g.define({subgoal_update:{id:'G1',reason:'bad edge',depends_on:['G1']}}),/cyclic/);
  assert.throws(()=>g.define({subgoal_update:{id:'G1',reason:'bad path',targets:['../outside.py']}}),/relative/);
  assert.deepEqual(g.state,before);
});

test('R4 subgoals: binding requires complete real bash evidence, never a model pass flag',()=>{
  for (const patch of [{complete:false},{executed:false},{tool:'read'},{jobStage:'running'},{exitCode:null},{id:'E999'}]) {
    const g=make(); assert.throws(()=>g.bindVerification({...binding(),passed:true},{E1:row(patch)},deps),/complete actual/);
    assert.equal(g.state.items.G1.proof,null);
  }
  assert.throws(()=>make().bindVerification(binding(),{},deps),/complete actual/);
});

test('R4 subgoals: successful evidence cannot bind after relevant source changes or with unknown fingerprints',()=>{
  for (const current of [{...deps,'main.py':'file:changed'},{'main.py':'unknown'},{}]) {
    const g=make(); assert.equal(g.bindVerification(binding(),{E1:row()},current).passed,false); assert.equal(g.state.items.G1.proof,null);
  }
  const g=make(); assert.equal(g.bindVerification(binding(),{E1:row({dependenciesBefore:{...deps,'main.py':'file:old'}})},deps).passed,false);
});

test('R4 subgoals: failure, absent assertion and unverified prerequisite cannot pass',()=>{
  for (const patch of [{clean:false},{exitCode:1},{stdout:'only 30 passed'}]) assert.equal(make().bindVerification(binding(),{E1:row(patch)},deps).passed,false);
  const g=make(); g.define({subgoal_plan:[{...goal,id:'G2',depends_on:['G1']}]});
  assert.equal(g.bindVerification({...binding(),subgoal_id:'G2'},{E1:row()},deps).passed,false);
});

test('R4 subgoals: duplicate binding is idempotent and latest contrary evidence cannot be hidden',()=>{
  const g=make(); g.bindVerification(binding(),{E1:row()},deps);
  assert.equal(g.bindVerification(binding(),{E1:row()},deps).duplicate,true); assert.equal(g.state.items.G1.checks,1);
  const failed=row({id:'E2',exitCode:1,clean:false,stdout:'failed'});
  assert.throws(()=>g.bindVerification(binding(),{E1:row(),E2:failed},deps),/later execution/);
  assert.equal(g.bindVerification(binding(1,'E2'),{E1:row(),E2:failed},deps).passed,false);
  g.bindVerification(binding(1,'E2'),{E1:row(),E2:failed},deps); assert.equal(g.state.items.G1.checks,2);
});

test('R4 subgoals: existing snapshots gain a revision without losing evidence',()=>{
  const g=make();g.observe(row()); const state=structuredClone(g.state);
  delete state.items.G1.revision; delete state.items.G1.history;
  const restored=new Subgoals(state);assert.equal(restored.state.items.G1.revision,1); assert.equal(restored.state.items.G1.proof.evidence,'E1');
  restored.sync(deps,true);assert.equal(restored.state.items.G1.status,'needs_recheck');assert.equal(restored.state.items.G1.proof,null);
});
