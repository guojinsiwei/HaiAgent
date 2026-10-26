import test from 'node:test';
import assert from 'node:assert/strict';
import {Policy} from '../src/policy.mjs';
import {FullTask} from '../src/full-task.mjs';
import {selectAnchors,validateExperiment} from '../src/exploration-learning.mjs';
const S='sha256:start',T='sha256:repaired';
const call=(id,command='python check.py')=>({name:'bash',callId:id,arguments:{command}});
const out=(stdout='',extra={})=>({executed:true,complete:true,exitCode:0,clean:true,stdout,stderr:'',...extra});
const experiment=()=>({hypothesis:'service is listening locally',alternative:'no listener exists',measurement:'count listening sockets on target port',supports:{field:'stdout',metric:'listeners',op:'gt',value:0},refutes:{field:'stdout',metric:'listeners',op:'lte',value:0}});
const proposal=(c)=>({tool:'bash',arguments:c.arguments,changed_dimensions:['target_dimension'],
 orthogonality_proof:{dependency_dimension:'same environment',target_dimension:'inspect sockets',command_dimension:'same shell'},exploration:experiment()});
function active(config={}) {const p=new Policy(config);for(const id of ['a','b'])p.observe(call(id),out('',{exitCode:1,stderr:'connection failed'}),S,S);return p;}
function dispatch(p,c,result,scope=S) {
 const plan=proposal(c),last=p.state.experiments.at(-1);if(last)plan.result_decision={result_id:last.id,action:'revise',reason:'inspect the changed listener condition'};
 assert.equal(p.propose(plan).accepted,true);
 assert.equal(p.before(c,scope).allowed,true);
 p.noteAction(c);p.executionStep(c.callId);p.observe(c,result,scope,scope);
}
test('triggering route outranks unrelated recent failures; duplicates merge',()=>{
 const rows=[{id:'E1',check_key:'a',command:'compile',scope:S},{id:'E2',check_key:'a',command:'compile',scope:T},
  {id:'E3',check_key:'b',command:'ls'}];
 const selected=selectAnchors(rows,{triggerKey:'a',query:'compiler'});
 assert.equal(selected.length,1);assert.equal(selected[0].attempts,2);assert.deepEqual(selected[0].evidence_ids,['E1','E2']);
 assert.equal(selected[0].conditions_changed,true);
});
test('one changed dimension accepted; no change rejected; predictions required',()=>{
 const p=active(),plan=proposal(call('probe','ss -lnt'));
 assert.equal(p.propose(plan).accepted,true);
 assert.equal(p.propose({...plan,changed_dimensions:[]}).accepted,false);
 assert.equal(p.propose({...plan,exploration:undefined}).accepted,false);
 assert.throws(()=>validateExperiment({...experiment(),refutes:{field:'stdout',contains:'{"listeners":1}'}}));
});
test('real result is written, retrievable on next step and survives restore',()=>{
 const p=active();dispatch(p,call('probe','ss -lnt'),out('{"listeners":0}'));
 const memory=p.state.experiments[0];assert.equal(memory.status,'refuted');assert.equal(memory.evidence_id,'E3');
 assert.deepEqual(memory.evidence,[{field:'stdout',metric:'listeners',value:0,op:'gt',threshold:0}]);assert.equal(memory.semantic_verified,false);
 assert.equal(new Policy({},p.state).explorationResults(S)[0].status,'refuted');
 assert.match(p.context(),/listeners/);
});
test('both, neither, incomplete, timeout and suspect execution all stay unknown',()=>{
 for(const result of [out('{"listeners":0}\n{"listeners":1}'),out('other'),out('{"listeners":0}',{complete:false}),out('{"listeners":0}',{timedOut:true}),out('{"listeners":0}',{clean:false})]) {
  const p=active();dispatch(p,call('probe','ss -lnt'),result);
  assert.equal(p.state.experiments[0].status,'unknown');
 }
});
test('matching support records observed condition without claiming correctness',()=>{
 const p=active();dispatch(p,call('probe','ss -lnt'),out('{"listeners":1}'));
 assert.equal(p.state.experiments[0].status,'supported');assert.equal(p.state.experiments[0].task_success,null);
});
test('no outcome fabricated for declaration, rejection or mismatched action',()=>{
 const p=active();p.propose(proposal(call('probe','ss -lnt')));
 assert.equal(p.before(call('mismatch','different'),S).allowed,false);
 p.observe(call('mismatch','different'),out('{"listeners":0}'),S,S);
 assert.equal(p.state.experiments.length,0);
});
test('routine actions use total allowance without consuming probe allowance',()=>{
 const p=active({explorationMaxExecutions:2});
 for(let i=0;i<3;i++)p.executionStep('read'+i);
 assert.equal(p.state.active,true);assert.equal(p.state.episode.executions,0);
 dispatch(p,call('p1','ss -lnt'),out('{"listeners":0}'));
 assert.equal(p.state.active,true);
 dispatch(p,call('p2','inspect-service-config'),out('{"listeners":1}'));
 assert.equal(p.state.active,false);assert.equal(p.state.experiments.length,2);
 assert.equal(p.state.episode.lastExit.auxiliaryExecutions,3);
});
test('verification after repair does not consume probe allowance',()=>{
 const p=active();const c=call('verify');assert.equal(p.before(c,T).allowed,true);
 p.executionStep(c.callId);assert.equal(p.state.episode.executions,0);
 p.observe(c,out('all passed'),T,T);assert.equal(p.state.active,false);
});
test('full task writes uncertain and local-defect results before routing exclusions',()=>{
 for(const result of [out('{"listeners":0}',{complete:false}),out('{"listeners":0}',{exitCode:1,stderr:'SyntaxError: broken'})]) {
  const p=active(),task=new FullTask({}),c=call('probe','ss -lnt');
  p.propose(proposal(c));assert.equal(task.before(c,p,S).allowed,true);p.executionStep(c.callId);
  task.observe(c,result,S,S,{}, {},p,'fixture');
  assert.equal(p.state.experiments.length,1);assert.equal(p.state.experiments[0].status,'unknown');
 }
});
test('result memory stays visible in full context and condition changes remain explicit',()=>{
 const p=active(),task=new FullTask({});dispatch(p,call('probe','ss -lnt'),out('{"listeners":0}'));
 task.state.scope=T;task.state.notices=Array(30).fill('noise'.repeat(1000));
 const panel=task.panel(p).result;
 assert.equal(panel.exploration.results[0].status,'refuted');
 assert.equal(panel.exploration.results[0].applicability,'historical_conditions_recheck');
});
test('duplicate receipt cannot create a second lesson, independent tasks stay isolated',()=>{
 const p=active(),c=call('probe','ss -lnt');dispatch(p,c,out('{"listeners":0}'));p.observe(c,out('{"listeners":0}'),S,S);
 assert.equal(p.state.experiments.length,1);assert.equal(new Policy().state.experiments.length,0);
});
test('opposing results preserve both observations rather than overwriting history',()=>{
 const p=active();dispatch(p,call('p1','ss -lnt'),out('{"listeners":0}'));
 dispatch(p,call('p2','inspect-listener'),out('{"listeners":1}'),T);
 assert.deepEqual(p.explorationResults(T).map(x=>x.status),['supported','refuted']);
});
test('uncertain core receipts have unique evidence IDs and protocol errors exit boundedly',()=>{
 const p=active();dispatch(p,call('p1','ss -lnt'),out('{"listeners":0}',{complete:false}));
 dispatch(p,call('p2','inspect-service-config'),out('{"listeners":1}'));
 assert.deepEqual(p.state.experiments.map(x=>x.evidence_id),['E3','E4']);
 const q=active();q.deny('Exploration predictions must distinguish support from refutation.');
 q.deny('Exploration predictions must distinguish support from refutation.');assert.equal(q.state.active,false);
});
