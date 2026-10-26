import test from 'node:test';
import assert from 'node:assert/strict';
import {Policy} from '../src/policy.mjs';
import {FullTask} from '../src/full-task.mjs';
import {checkIdentity} from '../src/exploration-trigger.mjs';
import {validateMeasurement,measure} from '../src/exploration-measurement.mjs';
const S='sha256:unchanged',T='sha256:repaired';
const call=(id,command)=>({name:'bash',callId:id,arguments:{command,workdir:'/app'}});
const out=(extra={})=>({executed:true,complete:true,exitCode:1,stdout:'',stderr:'AssertionError: boundary mismatch',clean:true,...extra});
function observe(p,id,command,extra={}){return p.observe(call(id,command),out(extra),S,S);}
const exp=()=>({hypothesis:'boundary case loses an item',alternative:'boundary case preserves its item',measurement:'count missing IDs from public API output on boundary and interior controls',supports:{field:'stdout',metric:'missing_ids',op:'gt',value:0},refutes:{field:'stdout',metric:'missing_ids',op:'lte',value:0}});
const plan=c=>({tool:'bash',arguments:c.arguments,changed_dimensions:['target_dimension'],orthogonality_proof:{dependency_dimension:'same implementation',target_dimension:'boundary and interior controls',command_dimension:'same test driver'},exploration:exp()});
function active(){const p=new Policy();observe(p,'a','python check.py');observe(p,'b','python check.py');return p;}

test('different checks at the same unresolved goal aggregate; other goals and targets stay separate',()=>{
  const p=new Policy();p.state.focus={goal:'G1',targets:['parser.py']};
  observe(p,'a','python test_boundary.py');observe(p,'b','python test_end.py');
  assert.equal(p.state.active,true);assert.deepEqual(p.state.episode.trigger.evidence,['E1','E2']);
  assert.equal(p.state.episode.baselineKeys.length,2);assert.equal(p.anchors().length,2);
  for(const focus of [{goal:'G2',targets:['parser.py']},{goal:'G1',targets:['socket.py']}]) {
    const q=new Policy();q.state.focus={goal:'G1',targets:['parser.py']};observe(q,'a','python test_boundary.py');
    q.state.focus=focus;observe(q,'b','python test_end.py');assert.equal(q.state.active,false);
  }
});
test('successful unrelated reads cannot erase repeated issue evidence; known repaired check clears it',()=>{
  const p=new Policy();p.state.focus={goal:'G1',targets:['parser.py']};observe(p,'a','python test_boundary.py');
  observe(p,'read','cat parser.py',{exitCode:0,stderr:'',stdout:'source'});
  observe(p,'b','python test_end.py');assert.equal(p.state.active,true);
  const q=new Policy();q.state.focus=p.state.focus;observe(q,'a','python test_boundary.py');
  observe(q,'ok','python test_boundary.py',{exitCode:0,stderr:''});observe(q,'b','python test_end.py');assert.equal(q.state.active,false);
});
test('pytest verbosity groups checks; selected case, cwd and command content stay distinct',()=>{
  assert.equal(checkIdentity('pytest -q tests/test_x.py'),checkIdentity('python -m pytest -vv tests/test_x.py --tb=short'));
  assert.notEqual(checkIdentity('pytest tests/test_x.py -k edge'),checkIdentity('pytest tests/test_x.py -k center'));
  assert.notEqual(checkIdentity('pytest tests/test_x.py','/a'),checkIdentity('pytest tests/test_x.py','/b'));
  assert.notEqual(checkIdentity('python -c "a()"'),checkIdentity('python -c "b()"'));
});
test('semantic stalled monitor activates from two real complete observations even with exit zero; replay is deduplicated',()=>{
  const p=new Policy(),task=new FullTask({});
  const evidence={E1:{id:'E1',complete:true,exitCode:0},E2:{id:'E2',complete:true,exitCode:0}};
  const review={verdict:'stalled',reason:'Two probes repeat the same fact',evidence_ids:['E1','E2'],next_check:'test boundary input',memories:[]};
  task.acceptMonitor(review,evidence);assert.equal(p.observeMonitor(review,evidence),true);
  assert.equal(p.state.episode.trigger.failures,0);assert.equal(p.state.episode.trigger.reason,'monitor_stalled_with_execution_evidence');
  p.endEpisode('test');for(let i=0;i<4;i++)p.executionStep('cooldown'+i);
  assert.equal(p.observeMonitor(review,evidence),false);
});
test('missing, control-only, stale, truncated and publicly progressing monitor evidence cannot force exploration',()=>{
  const review={verdict:'stalled',evidence_ids:['E1','E2'],next_check:'boundary input'};
  for(const evidence of [{},{E1:{complete:true}},{E1:{complete:true},E2:{complete:false}},
    {E1:{complete:true},E2:{complete:true,checkStatus:'public_check_passed'}},
    {E1:{complete:true},E2:{complete:true},E20:{complete:true}}])assert.equal(new Policy().observeMonitor(review,evidence),false);
});
test('filename and error-label matches remain observation-only, including historical root-cause false support',()=>{
  for(const literal of ['/app/cert.pem','checksum mismatch']){
    const e=validateMeasurement({hypothesis:'generated certificate bytes match original',supports:{field:'stdout',contains:literal},refutes:{field:'stderr',contains:'other'}});
    const r=measure(e,{stdout:literal,stderr:''},true);assert.equal(r.status,'unknown');assert.equal(r.reason,'literal_observation_only');assert.equal(r.evidence.length,1);
  }
});
test('boundary measurement separates explanations; missing, conflicting and mistyped values remain unknown',()=>{
  const e=validateMeasurement(exp());
  assert.equal(measure(e,{stdout:'{"missing_ids":2}'},true).status,'supported');
  assert.equal(measure(e,{stdout:'{"missing_ids":0}'},true).status,'refuted');
  for(const stdout of ['boundary check ran','{"missing_ids":"0"}','{"missing_ids":0}\n{"missing_ids":2}','{"missing_ids":null}'])assert.equal(measure(e,{stdout},true).status,'unknown');
  assert.equal(measure(e,{stdout:'{"missing_ids":0}'},false).status,'unknown');
  assert.throws(()=>validateMeasurement({...exp(),refutes:{field:'stdout',metric:'missing_ids',op:'eq',value:5}}));
});
test('a changed boundary test can share vocabulary while the exact failed action stays guarded',()=>{
  const p=active(),c=call('boundary','python check.py --boundary');
  assert.equal(p.propose(plan(c)).accepted,true);assert.equal(p.before(c,S).allowed,true);
  const q=active(),same=call('repeat','python check.py');q.propose(plan(same));assert.equal(q.before(same,S).allowed,false);
  assert.equal(q.before(same,T).allowed,true);
});
test('a measured result must be referenced by next probe; mismatch cannot execute or manufacture use',()=>{
  const p=active(),c=call('probe','python boundary.py');p.propose(plan(c));assert.equal(p.before(c,S).allowed,true);
  p.executionStep(c.callId);p.observe(c,out({exitCode:0,stderr:'',stdout:'{"missing_ids":0}'}),S,S);
  const next=call('next','python interior.py'),proposal=plan(next);
  assert.equal(p.propose(proposal).accepted,false);
  proposal.result_decision={result_id:p.state.experiments[0].id,action:'revise',reason:'boundary loss was refuted; check mutation of the interior value'};
  assert.equal(p.propose(proposal).accepted,true);
  assert.equal(p.before(call('wrong','python unrelated.py'),S).allowed,false);
  assert.equal(p.learningEvents.some(e=>e.event==='exploration_result_used'),false);
  assert.equal(p.propose(proposal).accepted,true);assert.equal(p.before(next,S).allowed,true);
  p.observe(next,out({exitCode:0,stderr:'',stdout:'{"missing_ids":1}'}),S,S);
  assert.equal(p.learningEvents.filter(e=>e.event==='exploration_result_used').length,1);
});
test('auxiliary work and malformed plans exit the gate without ending the task or injecting a command',()=>{
  const p=active();for(let i=0;i<16;i++)p.executionStep('read'+i);
  assert.equal(p.state.active,false);assert.equal(p.state.episode.lastExit.reason,'total_action_window_complete');
  assert.equal(p.before(call('fresh','python newcheck.py'),S).allowed,true);
  const q=active();for(let i=0;i<2;i++)q.deny('Exploration follow-up: missing result decision');
  assert.equal(q.state.active,false);assert.equal(q.before(call('fresh','python newcheck.py'),S).allowed,true);
});
test('timeout is never cached as a stable failure; completing another failing diagnostic does not close active issue',()=>{
  const p=new Policy();observe(p,'timeout','make qemu',{timedOut:true,exitCode:124});assert.equal(p.state.memories.length,0);
  assert.equal(p.before(call('retry','make qemu'),S).allowed,true);
  const q=active();observe(q,'other','python unrelated.py');observe(q,'fixed','python unrelated.py',{exitCode:0,stderr:''});
  assert.equal(q.state.active,true);
});
