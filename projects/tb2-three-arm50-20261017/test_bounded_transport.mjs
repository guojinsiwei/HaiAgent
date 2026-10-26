import test from 'node:test';
import assert from 'node:assert/strict';
import {costUsage,SpendingClient} from './spending-client.mjs';
test('peak estimate separates cache, output and input; never double charges cache at uncached rate',()=>{
  assert.equal(costUsage({input_tokens:1000000,cache_read_input_tokens:1000000,output_tokens:1000000}),10040000);
  assert.equal(costUsage({input_tokens:0,output_tokens:0,cache_read_input_tokens:1}),1);
  assert.equal(costUsage({input_tokens:1}),null);
});
test('unknown accounting stops current solver without creating a campaign halt',async()=>{
  const client=new SpendingClient({});const calls=[];
  client.call=async(path,value)=>{calls.push({path,value});return {halt_reason:null,task_halt_reason:'usage_unavailable'};};
  await assert.rejects(client.settle('lease',null),/usage_unavailable/);
  assert.deepEqual(calls.map(x=>x.path),['/settle']);
});
test('provider halt includes the task identity',async()=>{
  const client=new SpendingClient({CAMPAIGN_BUDGET_URL:'http://fixture',CAMPAIGN_BUDGET_JOB:'second'});let captured;
  client.call=async(path,value)=>{captured={path,value};};
  await client.halt('provider_credentials');
  assert.deepEqual(captured,{path:'/halt',value:{reason:'provider_credentials',job:'second'}});
});
test('total exhaustion is latched for supervisor before stopping the request',async()=>{
  const client=new SpendingClient({CAMPAIGN_BUDGET_URL:'http://fixture',CAMPAIGN_BUDGET_JOB:'second'});const calls=[];
  client.call=async(path,value)=>{calls.push({path,value});if(path==='/reserve')throw Error('campaign_budget_exhausted');return {};};
  await assert.rejects(client.reserve('endpoint',{body:'{"model":"model","max_tokens":16}'}),/campaign_budget_exhausted/);
  assert.deepEqual(calls.map(x=>x.path),['/reserve','/halt']);
  assert.equal(calls[1].value.reason,'campaign_budget_exhausted');
});
