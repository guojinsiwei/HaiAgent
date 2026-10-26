import test from 'node:test';
import assert from 'node:assert/strict';
import { CriticCache } from '../src/critic-cache.mjs';
import { FullTask } from '../src/full-task.mjs';
import { Policy } from '../src/policy.mjs';
import { bashObservation } from '../src/workspace.mjs';
import { extractOutcome } from '../src/terminal.mjs';

test('R5 an early subgoal without verification cannot crash Critic cache eligibility',()=>{
  const task=new FullTask({});
  task.goals.define({subgoal_plan:[{id:'G1',title:'Implement',acceptance:'Public tests pass',targets:['main.py'],depends_on:[]}]});
  assert.equal(new CriticCache().eligible({arguments:{command:'python check.py'},cache_scope:'workspace'},task),false);
  assert.equal(new CriticCache().eligible({arguments:{command:'cat main.py'},cache_scope:'workspace'},task),true);
});

test('R5 restored Advisor cooldown uses bounded new-clock units, while first call is never delayed',()=>{
  const fresh=new FullTask({});assert.equal(fresh.state.lastAdvisorClock,undefined);
  const saved=fresh.snapshot();saved.observed=12;saved.advisorCalls=1;saved.lastAdvisorTool=500;
  delete saved.recoveryClock;
  const restored=new FullTask({},saved);assert.equal(restored.state.lastAdvisorClock,12);
  const again=new FullTask({},structuredClone(restored.snapshot()));assert.equal(again.state.lastAdvisorClock,12);
});

test('R5 sandbox failures and interrupted native Bash results are not clean executed evidence',()=>{
  const base={kind:'foreground',exitCode:0,stdout:{text:'passed',truncated:false},stderr:{text:'',truncated:false}};
  for(const sandbox of [{denied:true},{runnerFailed:true}]){
    const out=bashObservation({value:{...base,sandbox}});
    assert.equal(out.executed,false);assert.equal(out.complete,false);assert.deepEqual(out.sandbox,sandbox);
  }
  for(const flag of ['timedOut','aborted','stopped','signal']){
    const out=bashObservation({value:{...base,[flag]:true}});
    assert.equal(out.complete,false);assert.equal(out[flag],true);
  }
});

test('R5 upstream nonzero cannot create a successful pipeline memory or a semantic failure ban',()=>{
  const args={command:'false | cat'},receipt={status:'verified',allSucceeded:false,stages:[{exitCode:1},{exitCode:0}]};
  const raw={executed:true,complete:true,exitCode:0,stdout:'',stderr:'',shellStageReceipt:receipt};
  const out=extractOutcome(args,raw);assert.equal(out.clean,false);assert.equal(out.pipelineNonzero,true);
  assert.equal(out.failureObserved,false);assert.equal(out.taskSuccess,null);
  const task=new FullTask({}),policy=new Policy();
  task.observe({name:'bash',callId:'C1',arguments:args},raw,'sha256:s','sha256:s',{}, {},policy,'native');
  assert.equal(policy.state.memories.length,0);assert.equal(task.state.evidence.E1.shellStageCoverage,'verified_top_level_pipeline');
  const clean=extractOutcome(args,{...raw,shellStageReceipt:{...receipt,allSucceeded:true,stages:[{exitCode:0},{exitCode:0}]}});
  assert.equal(clean.clean,true);assert.equal(clean.taskSuccess,null);
  assert.equal(extractOutcome(args,{...raw,shellStageReceipt:{status:'unknown'}}).clean,false);
});
