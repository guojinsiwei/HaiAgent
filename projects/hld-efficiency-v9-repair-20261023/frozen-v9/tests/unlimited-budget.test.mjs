import test from 'node:test';
import assert from 'node:assert/strict';
import {installFull} from '../src/full-integration.mjs';
import {FullTask} from '../src/full-task.mjs';
import {progressView} from '../src/progress.mjs';

function hooks(input){
  const events=new Map(),full=new FullTask(input),entry={full};
  const ctx={on:(n,fn)=>events.set(n,fn),tools:{register(){}}};
  installFull(ctx,{input,root:'.',audit:'.',stateFor:()=>entry,persist(){},entries:new Map([['s',entry]])});
  return{events,full};
}
const exhaust=async iter=>{for await(const x of iter){};};
async function* response(){yield{type:'usage',usage:{inputTokens:100,outputTokens:10}};yield{type:'finish',reason:{kind:'stop'}};}

test('unlimited bypasses all old caps but counts requests/tools/usage',async()=>{
  const input={budgetDisabled:true,maxRequests:1,maxTools:1,wallSeconds:.001,costPolicy:{invalid:'old policy ignored'}};
  const{events,full}=hooks(input);full.state.startedAt=1;full.state.usage.requests=800;full.state.usage.tools=600;
  full.state.cost={boundExceeded:true};
  await exhaust(events.get('llm/stream')({sessionId:'s',purpose:'compaction'},response));
  assert.equal(full.state.usage.requests,801);assert.equal(full.state.usage.inputTokens,100);
  assert.equal((await events.get('tools/pre-execute')({agent:{}},async()=>({kind:'allow'}))).kind,'allow');
  assert.equal(await events.get('tools/execute')({agent:{},name:'read',callId:'x'},async()=>42),42);
  assert.equal(full.state.usage.tools,601);
});
test('bounded default still rejects exhausted budget',async()=>{
  const{events,full}=hooks({maxRequests:1});full.state.usage.requests=1;
  await assert.rejects(exhaust(events.get('llm/stream')({sessionId:'s'},response)),/request budget/);
});
test('unlimited does not bypass host denial',async()=>{
  const{events}=hooks({budgetDisabled:true});
  assert.deepEqual(await events.get('tools/pre-execute')({agent:{}},async()=>({kind:'deny',reason:'host'})),{kind:'deny',reason:'host'});
});
test('unlimited has no stale percentage-based delivery pressure',()=>{
  const f=new FullTask({budgetDisabled:true});f.state.usage.requests=50000;f.state.usage.tools=50000;
  progressView(f.state,f.config,{});assert.equal(f.state.budgetView.phase,'unlimited');assert.equal(f.state.budgetView.maxRequests,null);
});
test('monitor remains reachable after former lifetime quota',()=>{
  const f=new FullTask({budgetDisabled:true});f.state.monitorCalls=90;f.state.observed=1000;f.state.lastMonitor=975;f.state.lastMonitorClock=970;
  assert.equal(f.monitorLane(),'periodic');
  const b=new FullTask({});b.state.monitorCalls=12;b.state.observed=1000;assert.equal(b.monitorLane(),null);
});
test('unlimited still validates mode type and retains cooldown',()=>{
  assert.throws(()=>hooks({budgetDisabled:'true'}),/budgetDisabled/);
  const f=new FullTask({budgetDisabled:true});f.state.observed=100;f.state.lastMonitorClock=99;
  assert.equal(f.monitorLane(),null);
});
