import test from 'node:test';
import assert from 'node:assert/strict';
import {Subgoals} from '../src/subgoals.mjs';
import {SubgoalController} from '../src/subgoal-controller.mjs';
import {actionKey} from '../src/policy.mjs';

const deps={'a.py':'file:a','b.py':'file:b'},args={command:'python -m pytest test_a.py'};
const goal=(id='G1',extra={})=>({id,title:'public parser behavior',acceptance:'public parser check passes',targets:['a.py'],depends_on:[],...extra});
const verify={arguments:args,stdout_contains:['31 passed']};
const row=(extra={})=>({id:'E1',tool:'bash',executed:true,complete:true,clean:true,exitCode:0,category:'test',command:args.command,arguments:args,key:actionKey({name:'bash',arguments:args}),stdout:'31 passed',stderr:'',dependenciesBefore:deps,dependenciesAfter:deps,after:'sha256:a',...extra});
const fixture=(plan=[goal()])=>{const goals=new Subgoals();goals.define({subgoal_plan:plan});return {goals,controller:new SubgoalController()};};

test('R5 subgoal controller: early plan request is bounded and never blocks',()=>{
  const goals=new Subgoals(),c=new SubgoalController();
  const first=c.tick(goals,{dependencies:deps});assert.match(first.notice,/Establish concrete subgoals/);assert.equal(first.view.blocking,false);
  for(let n=0;n<8;n++)assert.equal(c.tick(goals,{dependencies:deps,observed:1,requests:1}).notice,null);
  assert.match(c.tick(goals,{dependencies:deps,observed:3,requests:3}).notice,/subgoal_plan/);
  for(let n=4;n<100;n++)assert.equal(c.tick(goals,{dependencies:deps,observed:n,requests:n}).notice,null);
  assert.equal(c.state.planPrompts,2);assert.equal(Object.keys(goals.state.items).length,0);
});

test('R5 subgoal controller: saved reminder state survives a restart without resetting allowance',()=>{
  const goals=new Subgoals(),c=new SubgoalController();c.tick(goals,{});
  const restored=new SubgoalController(JSON.parse(JSON.stringify(c.state)));assert.equal(restored.tick(goals,{}).notice,null);
  restored.tick(goals,{observed:3});assert.equal(restored.state.planPrompts,2);
});

test('R5 subgoal controller: existing meaningful plan avoids the planner prompt',()=>{
  const {goals,controller}=fixture(),r=controller.tick(goals,{dependencies:deps});
  assert.equal(r.notice,null);assert.equal(r.view.active,'G1');assert.equal(r.view.mode,'working');assert.equal(controller.state.planPrompts,0);
});

test('R5 subgoal controller: real clean candidate is shown once with exact E/native arguments but never auto-passed',()=>{
  const {goals,controller}=fixture(),evidence={E1:row()};const result=controller.tick(goals,{dependencies:deps,evidence});
  assert.equal(result.view.verification_candidates[0].evidence_id,'E1');assert.deepEqual(result.view.verification_candidates[0].arguments,args);
  assert.match(result.notice,/Coverage is NOT automatic/);assert.equal(goals.state.items.G1.status,'pending');assert.equal(goals.state.items.G1.proof,null);
  assert.equal(controller.tick(goals,{dependencies:deps,evidence}).notice,null);
  assert.equal(controller.tick(goals,{dependencies:deps,evidence}).view.verification_candidates.length,1);
});

test('R5 subgoal controller: echo/cat/grep and unregistered complex commands are not test candidates',()=>{
  for(const command of ['echo PASS','cat report.txt','grep passed report.txt','cd src && python custom.py']) {
    const {goals,controller}=fixture(),arguments_={command},r=row({command,arguments:arguments_,category:'generic',key:actionKey({name:'bash',arguments:arguments_})});
    assert.equal(controller.tick(goals,{dependencies:deps,evidence:{E1:r}}).view.verification_candidates.length,0);
  }
  const command='cat report.txt',arguments_={command};
  const {goals,controller}=fixture([goal('G1',{verification:{arguments:arguments_,stdout_contains:['passed']}})]);
  assert.equal(controller.tick(goals,{dependencies:deps,evidence:{E1:row({command,arguments:arguments_,category:'read',key:actionKey({name:'bash',arguments:arguments_})})}}).view.verification_candidates.length,0);
});

test('R5 subgoal controller: explicitly registered generic command is eligible; unknown full arguments are never guessed',()=>{
  const {goals,controller}=fixture([goal('G1',{verification:verify})]),evidence={E1:row({category:'generic',arguments:undefined})};
  const candidate=controller.tick(goals,{dependencies:deps,evidence}).view.verification_candidates[0];
  assert.equal(candidate.exact_registered_check,true);assert.equal(candidate.arguments_unavailable,true);assert.equal(candidate.arguments,undefined);
});

test('R5 subgoal controller: dirty/incomplete/changed-source and superseded checks produce no candidates',()=>{
  for(const patch of [{clean:false},{complete:false},{exitCode:1},{tool:'read'},{executed:false},{jobStage:'running'},{dependenciesBefore:{'a.py':'file:old'}}]) {
    const {goals,controller}=fixture();assert.equal(controller.tick(goals,{dependencies:deps,evidence:{E1:row(patch)}}).view.verification_candidates.length,0);
  }
  const {goals,controller}=fixture();assert.equal(controller.tick(goals,{dependencies:{'a.py':'file:new'},evidence:{E1:row()}}).view.verification_candidates.length,0);
  assert.equal(controller.tick(goals,{dependencies:deps,evidence:{E1:row(),E2:row({id:'E2',exitCode:1,clean:false})}}).view.verification_candidates.length,0);
});

test('R5 subgoal controller: actual check automatically advances focus to the next ready dependency',()=>{
  const {goals,controller}=fixture([goal('G1',{verification:verify}),goal('G2',{depends_on:['G1'],targets:['b.py']})]);
  controller.tick(goals,{dependencies:deps});assert.equal(goals.state.active,'G1');goals.observe(row());
  assert.equal(goals.state.items.G1.status,'check_passed');assert.equal(goals.state.active,'G2');
  const r=controller.tick(goals,{dependencies:deps});assert.equal(r.view.active,'G2');assert.deepEqual(r.view.ready,['G2']);
});

test('R5 subgoal controller: failure or changed source moves focus back and invalidates downstream proof',()=>{
  const args2={command:'python -m pytest test_b.py'},verify2={arguments:args2,stdout_contains:['31 passed']};
  for(const kind of ['failure','source']) {
    const {goals,controller}=fixture([goal('G1',{verification:verify}),goal('G2',{depends_on:['G1'],targets:['b.py'],verification:verify2})]);
    goals.observe(row());goals.observe(row({id:'E2',key:actionKey({name:'bash',arguments:args2})}));assert.equal(goals.state.active,null);
    if(kind==='failure')goals.observe(row({id:'E3',exitCode:1,clean:false,stdout:'failed'}));
    const current=kind==='source'?{...deps,'a.py':'file:changed'}:deps;const r=controller.tick(goals,{dependencies:current});
    assert.equal(r.view.active,'G1');assert.equal(goals.state.items.G2.status,'needs_recheck');assert.equal(goals.state.items.G2.proof,null);
  }
});

test('R5 subgoal controller: explicitly blocked/deferred goals are not force-reactivated by a matching check',()=>{
  for(const status of ['blocked','deferred']) {
    const {goals,controller}=fixture([goal('G1',{verification:verify})]);goals.define({subgoal_update:{id:'G1',status,reason:'requires another dependency'}});
    assert.deepEqual(goals.observe(row()),[]);const r=controller.tick(goals,{dependencies:deps,evidence:{E1:row()}});
    assert.equal(r.view.active,null);assert.equal(r.view.mode,'blocked_or_deferred');assert.equal(goals.state.items.G1.status,status);
  }
});

test('R5 subgoal controller: version changes require revalidation and all checks passed does not mean official success',()=>{
  const {goals,controller}=fixture([goal('G1',{verification:verify})]);goals.observe(row());
  assert.equal(controller.tick(goals,{dependencies:deps}).view.mode,'planned_checks_passed');assert.equal(controller.tick(goals,{dependencies:deps}).view.official_success,null);
  goals.define({subgoal_update:{id:'G1',reason:'new edge case',acceptance:'public parser edge cases pass'}});
  assert.equal(goals.state.active,'G1');assert.equal(goals.state.items.G1.proof,null);assert.equal(goals.state.items.G1.revision,2);
});

test('R5 subgoal controller: a proof from another revision cannot survive a state refresh',()=>{
  const {goals,controller}=fixture([goal('G1',{verification:verify})]);goals.observe(row());goals.state.items.G1.revision=2;
  controller.tick(goals,{dependencies:deps});assert.equal(goals.state.items.G1.status,'needs_recheck');assert.equal(goals.state.items.G1.proof,null);
});

test('R5 subgoal controller: successful silent doctest advances a predeclared goal without inventing output markers',()=>{
  const arguments_={command:'python3 -m doctest a.py'},verification={arguments:arguments_,exit_code:0,stdout_contains:[]};
  const {goals,controller}=fixture([goal('G1',{verification}),goal('G2',{depends_on:['G1']})]);
  const actual=row({command:arguments_.command,arguments:arguments_,category:'generic',stdout:'',key:actionKey({name:'bash',arguments:arguments_})});
  assert.equal(goals.observe(actual)[0].passed,true);assert.equal(goals.state.items.G1.status,'check_passed');
  assert.equal(controller.tick(goals,{dependencies:deps}).view.active,'G2');
});

test('R5 subgoal controller: an observed silent doctest is only a candidate until an explicit definition and real E binding',()=>{
  const arguments_={command:'python -m doctest a.py'},actual=row({command:arguments_.command,arguments:arguments_,category:'generic',stdout:'',key:actionKey({name:'bash',arguments:arguments_})});
  const {goals,controller}=fixture(),evidence={E1:actual};
  const result=controller.tick(goals,{dependencies:deps,evidence});assert.equal(result.view.verification_candidates.length,1);
  assert.match(result.notice,/do not invent a success marker/);assert.equal(goals.state.items.G1.status,'pending');
  goals.define({subgoal_update:{id:'G1',reason:'public doctest is silent on success',verification:{arguments:arguments_,exit_code:0,stdout_contains:[]}}});
  assert.equal(goals.bindVerification({subgoal_id:'G1',revision:2,evidence_id:'E1'},evidence,deps).passed,true);
});

test('R5 subgoals: empty assertions require explicit zero exit and a substantive check; trivial and generic commands are refused',()=>{
  for(const command of ['echo ok','true',':','cat a.py','grep passed report.txt','python -c "print(1)"','touch output.txt','python -m doctest','python -m doctest --help','pytest --collect-only']) {
    assert.throws(()=>fixture([goal('G1',{verification:{arguments:{command},exit_code:0,stdout_contains:[]}})]),/trivial|substantive/);
  }
  assert.throws(()=>fixture([goal('G1',{verification:{arguments:args,stdout_contains:[]}})]),/explicit exit_code/);
  assert.throws(()=>fixture([goal('G1',{verification:{arguments:args,exit_code:1,stdout_contains:['failed']}})]),/exit_code:0/);
});

test('R5 subgoals: silent checks still need complete executed clean receipts and unchanged targets',()=>{
  const arguments_={command:'python -m doctest a.py'},verification={arguments:arguments_,exit_code:0,stdout_contains:[]};
  for(const patch of [{complete:false},{complete:undefined},{executed:false},{executed:undefined},{exitCode:null},{exitCode:1},{clean:false},{nativeToolError:true},{dependenciesBefore:{'a.py':'file:old'}}]) {
    const {goals}=fixture([goal('G1',{verification})]),actual=row({command:arguments_.command,arguments:arguments_,stdout:'',key:actionKey({name:'bash',arguments:arguments_}),...patch});
    assert.equal(goals.observe(actual)[0].passed,false);assert.equal(goals.state.items.G1.proof,null);
  }
});
