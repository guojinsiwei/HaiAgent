import test from 'node:test';
import assert from 'node:assert/strict';
import { RecoveryClock } from '../src/recovery-clock.mjs';
import { FullTask } from '../src/full-task.mjs';
import { Policy } from '../src/policy.mjs';
const S='sha256:s';
const call=i=>({name:'bash',callId:`C${i}`,arguments:{command:'python check.py'}});

test('R5 recovery: native admission/final receipt count once; rejection is not execution evidence',()=>{
  const clock=new RecoveryClock();clock.execution(call(1));clock.execution(call(1));
  assert.equal(clock.state.steps,1);const rejected=clock.rejected(call(2),'blocked',S);
  assert.equal(clock.state.steps,2);assert.equal(rejected.executed,false);assert.equal(rejected.complete,false);
  assert.equal(clock.rejected(call(2),'blocked',S),null);
  assert.equal(new RecoveryClock(structuredClone(clock.state)).state.steps,2);
});
test('R5 recovery: rejected calls advance Monitor cooldown without creating E or failure anchors',()=>{
  const task=new FullTask({monitorCooldown:8}),policy=new Policy();
  task.state.scope=S;
  for(let i=1;i<=8;i++)task.recoveryRejected(call(i),'same failed command');
  assert.equal(task.state.observed,0);assert.deepEqual(task.state.evidence,{});assert.equal(policy.anchors().length,0);
  assert.equal(task.monitorLane(),'anomaly');assert.equal(task.monitorStarted(),'anomaly');
  assert.equal(task.monitorDue(),false);assert.equal(task.advisory.state.pending.trigger,'rejection_stall');
  assert.ok(task.advisory.state.pending.evidence_ids.every(id=>id.startsWith('R')));
});
test('R5 recovery: rejection monitoring preserves six later periodic slots and total cap',()=>{
  const task=new FullTask({monitorCooldown:3});task.state.scope=S;
  for(let n=0;n<6;n++){
    for(let k=0;k<3;k++)task.recoveryRejected(call(n*3+k),'blocked');
    assert.equal(task.monitorStarted(),'anomaly');
  }
  for(let k=20;k<23;k++)task.recoveryRejected(call(k),'blocked');
  assert.equal(task.monitorDue(),false);
  task.state.usage.tools=600;
  for(let n=0;n<6;n++){
    for(let k=0;k<3;k++)task.recoveryRejected(call(100+n*3+k),'blocked');
    assert.equal(task.monitorStarted(),'periodic');
  }
  assert.equal(task.state.monitorCalls,12);assert.equal(task.monitorDue(),false);
});
test('R5 recovery: Monitor may cite R for a control stall but not store a fake failure memory',()=>{
  const task=new FullTask({});task.state.scope=S;
  task.recoveryRejected(call(1),'format');task.recoveryRejected(call(2),'format');
  task.acceptMonitor({verdict:'stalled',reason:'format repeated',evidence_ids:[],control_ids:['R1','R2'],next_check:'inspect tool schema',memories:[{kind:'blocker',conclusion:'route failed',condition:'now',evidence_ids:['R1'],support:[{evidence_id:'R1',field:'stderr',quote:'error'}]}]}, {},task.clock.evidence());
  assert.equal(task.state.monitor.verdict,'stalled');assert.equal(task.memory.state.items.length,0);
  assert.throws(()=>task.acceptMonitor({verdict:'stalled',reason:'x',evidence_ids:[],control_ids:['R1','R404'],next_check:'x',memories:[]},{},task.clock.evidence()),/invalid monitor/);
});
test('R5 exploration: two orthogonality rejections exit without killing task or injecting commands',()=>{
  const p=new Policy();p.state.active=true;
  p.deny('Active exploration requires all three comparison fields');assert.equal(p.state.active,true);
  p.deny('command_similarity_above_threshold');assert.equal(p.state.active,false);
  assert.equal(p.state.episode.lastExit.reason,'orthogonal_rejections');assert.match(p.state.diagnosticHint,/read-only/);
  assert.equal(p.before({name:'bash',arguments:{command:'ls'}},S).allowed,true);
  assert.equal(p.state.advisory,false);
});
test('R5 exploration: admitted probes end the eight-probe window, polls do not duplicate a call',()=>{
  const p=new Policy();p.state.active=true;
  for(let i=1;i<=7;i++){p.executionStep(`C${i}`,'probe');p.executionStep(`C${i}`,'probe');}
  assert.equal(p.state.active,true);p.executionStep('C8','probe');assert.equal(p.state.active,false);
  assert.equal(p.state.episode.lastExit.executions,8);
});
test('R5 exploration: successful intervening admission resets consecutive orthogonal rejections',()=>{
  const p=new Policy();p.state.active=true;p.deny('command_similarity_above_threshold');p.executionStep('C1');p.deny('command_similarity_above_threshold');
  assert.equal(p.state.active,true);assert.equal(p.state.episode.rejections,1);
});

test('R5 exploration: cooldown uses four recovery steps, including rejections, never duplicated receipts',()=>{
  const p=new Policy();p.state.active=true;
  for(let i=0;i<8;i++)p.executionStep(`C${i}`,'probe');
  assert.equal(p.state.episode.cooldownRemaining,4);
  p.executionStep('C7');assert.equal(p.state.episode.cooldownRemaining,4);
  p.deny('format');p.executionStep('C8');p.executionStep('C8');p.deny('format');
  assert.equal(p.state.episode.cooldownRemaining,1);p.executionStep('C9');assert.equal(p.state.episode.cooldownRemaining,0);
});

test('R5 exploration: changed real inputs with unchanged error can start a new episode after cooldown',()=>{
  const p=new Policy(),failure={executed:true,complete:true,exitCode:1,stdout:'same failure',stderr:''};
  const actions=['A','B'].map(name=>({name:'bash',callId:name,arguments:{command:'python A.py'}}));
  for(const action of actions)p.observe(action,failure,S,S,{'input.py':'file:v1'});
  assert.equal(p.state.active,true);p.endEpisode('orthogonal_rejections');
  p.executionStep('inspect1');p.executionStep('inspect2');
  assert.equal(p.before(actions[0],'sha256:new',{dependencies:{'input.py':'file:v2'}}).reason,'observed_workspace_change');
  for(const action of [...actions, {...actions[1],callId:'C'}]) {
    p.executionStep(action.callId+':retry');p.observe(action,failure,'sha256:new','sha256:new',{'input.py':'file:v2'});
  }
  assert.equal(p.state.active,true);assert.equal(p.state.episode.serial,2);
  assert.equal(p.state.memories.at(-3).conditionsChanged,true);
});

test('R5 exploration: unchanged repeated failures do not rearm an exhausted gate',()=>{
  const p=new Policy(),failure={executed:true,complete:true,exitCode:1,stdout:'same failure',stderr:''};
  p.observe(call(1),failure,S,S);p.observe({...call(2),arguments:{command:'python other.py'}},failure,S,S);
  p.endEpisode('execution_window_complete');
  for(let i=0;i<4;i++)p.executionStep(`inspect${i}`);
  p.observe(call(3),failure,S,S);p.observe(call(4),failure,S,S);
  assert.equal(p.state.active,false);
});
