import test from 'node:test';
import assert from 'node:assert/strict';
import { Advisory } from '../src/advisory.mjs';
import { FullTask } from '../src/full-task.mjs';

const S='sha256:first',T='sha256:second';
const row=(id,extra={})=>({id,key:'command',before:S,after:S,rawHashes:{stdout:'a',stderr:'b'},exitCode:1,complete:true,failureObserved:true,clean:false,...extra});
const failure=a=>{for(let i=1;i<=3;i++)a.observe(row(`E${i}`),false,false);};
test('three actually observed identical failures queue one task-local handover',()=>{
  const a=new Advisory(null,{});a.observe(row('E1'),false,false);a.observe(row('E2'),false,false);assert.equal(a.state.pending,null);
  a.observe(row('E3'),false,false);assert.equal(a.state.pending.trigger,'repeated_failure');assert.deepEqual(a.state.pending.evidence_ids,['E1','E2','E3']);
  a.markAttempt(a.state.pending);a.observe(row('E4'),false,false);assert.equal(a.state.pending,null);
});
test('changed or unknown state, incomplete output, local syntax error cannot establish repeated failure',()=>{
  for(const extra of [{before:S,after:T},{before:'unknown',after:'unknown'},{complete:false},{failureObserved:false}]) {
    const a=new Advisory(null,{});for(let i=0;i<5;i++)a.observe(row(`E${i}`,extra),false,false);assert.equal(a.state.pending,null);
  }
  const a=new Advisory(null,{});for(let i=0;i<5;i++)a.observe(row(`E${i}`),false,true);assert.equal(a.state.pending,null);
});
test('different error output or an intervening execution resets consecutive failures',()=>{
  const a=new Advisory(null,{});a.observe(row('E1'),false,false);a.observe(row('E2'),false,false);
  a.observe(row('E3',{rawHashes:{stdout:'new',stderr:'new'}}),false,false);assert.equal(a.state.pending,null);
  a.observe(row('E4',{exitCode:0,clean:true,failureObserved:false}),false,false);assert.equal(a.state.failures.length,0);
});
test('fourteen observed read-only steps queue a suspicion, not an execution or failure claim',()=>{
  const a=new Advisory(null,{});
  for(let i=1;i<=13;i++)a.observe(row(`E${i}`,{exitCode:0,clean:true,failureObserved:false}),true,false);
  assert.equal(a.state.pending,null);a.observe(row('E14',{exitCode:0,clean:true,failureObserved:false}),true,false);
  assert.equal(a.state.pending.trigger,'extended_diagnosis');assert.match(a.state.pending.question,/does not prove stagnation/);assert.equal(a.state.pending.evidence_ids.length,3);
});
test('semantic stall takes priority; a new progress review cancels a pending alarm',()=>{
  const a=new Advisory(null,{});failure(a);
  a.monitor({verdict:'stalled',reason:'no new evidence',next_check:'inspect dependency',evidence_ids:['E2','E3']},{E2:row('E2'),E3:row('E3')},S);
  assert.equal(a.state.pending.trigger,'semantic_stall');a.monitor({verdict:'necessary_retry'},{},S);assert.equal(a.state.pending,null);
});
test('workspace change cancels stale pending advice; unknown state does not falsely claim progress',()=>{
  const a=new Advisory(null,{});failure(a);a.sync('unknown');assert.ok(a.state.pending);a.sync(T);assert.equal(a.state.pending,null);
});
test('pending handover and attempted signatures survive resume without cross-task leakage',()=>{
  const a=new Advisory(null,{});failure(a);const restored=new Advisory(JSON.parse(JSON.stringify(a.state)),{});
  assert.equal(restored.state.pending.trigger,'repeated_failure');restored.markAttempt(restored.state.pending);
  const again=new Advisory(JSON.parse(JSON.stringify(restored.state)),{});failure(again);assert.equal(again.state.pending,null);
  const fresh=new Advisory(null,{});failure(fresh);assert.ok(fresh.state.pending);
});
test('malformed optional memories do not suppress a valid monitor alarm; invalid verdict IDs do',()=>{
  const task=new FullTask({});task.state.scope=S;task.state.evidence={E1:row('E1'),E2:row('E2')};
  task.acceptMonitor({verdict:'stalled',reason:'same failure',next_check:'inspect',evidence_ids:['E1','E2'],memories:{}},task.state.evidence);
  assert.equal(task.advisory.state.pending.trigger,'semantic_stall');assert.equal(task.memory.state.items.length,0);
  const other=new FullTask({});assert.throws(()=>other.acceptMonitor({verdict:'stalled',reason:'x',next_check:'y',evidence_ids:['E99','E100'],memories:[]},{}));assert.equal(other.advisory.state.pending,null);
});
test('advisor limits are configurable and invalid values fail explicitly',()=>{
  assert.equal(new Advisory(null,{maxAdvisorCalls:0}).config.maxAdvisorCalls,0);
  for(const config of [{repeatedFailureThreshold:0},{diagnosticAdvisorThreshold:-1},{maxAdvisorCalls:-1},{advisorCooldownTools:0}])assert.throws(()=>new Advisory(null,config));
});
test('an intervening native edit resets old consecutive-failure counters even if files are restored',()=>{
  const a=new Advisory(null,{});a.observe(row('E1'),false,false);a.observe(row('E2'),false,false);
  a.sync(T);a.sync(S);a.observe(row('E3'),false,false);
  assert.equal(a.state.failures.length,1);assert.equal(a.state.pending,null);
});
