import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {reserveCost,settleCost} from './budget-v1.mjs';
import {SpendingClient,costUsage} from './spending-client.mjs';
const policy={limitCny:8,inputPerMillion:2,cacheReadPerMillion:.04,outputPerMillion:8,maxInputTokens:128000,maxOutputTokens:16384,provider:'p',model:'m',priceBasis:'pinned'};
test('cached usage equals shared ledger and permits calls under the real 8 CNY cap',()=>{
 const state={};const usage={inputTokens:10000,outputTokens:1000,cacheReadTokens:80000,cacheWriteTokens:0};
 for(let i=0;i<90;i++)settleCost(state,policy,reserveCost(state,policy,{provider:'p',model:'m',maxTokens:16384}),usage,true);
 const expected=90*costUsage({input_tokens:10000,output_tokens:1000,cache_read_input_tokens:80000})/1e6;
 assert.ok(Math.abs(state.cost.spentUpperCny-expected)<.0001);
 assert.ok(state.cost.spentUpperCny<3);
 assert.throws(()=>reserveCost({cost:{spentUpperCny:7.7,pendingUpperCny:0}},policy,{provider:'p',model:'m',maxTokens:16384}),/ceiling/);
});
test('unknown usage keeps full reservation',()=>{
 const s={};const reserve=reserveCost(s,policy,{provider:'p',model:'m',maxTokens:16384});settleCost(s,policy,reserve,null,false);
 assert.equal(s.cost.spentUpperCny,reserve);assert.equal(s.cost.uncertainAttempts,1);
});
test('lost reserve/settle responses replay the same identities, charge once, and never retry 402',async()=>{
 const rows=new Map();const seen=[];let deny=0;
 const server=http.createServer(async(req,res)=>{
  let text='';for await(const b of req)text+=b;const v=JSON.parse(text);seen.push([req.url,v]);
  if(req.url==='/deny'){deny++;res.writeHead(402);return res.end(JSON.stringify({error:'per_task_budget_exhausted'}));}
  const key=req.url+v.id;const first=!rows.has(key);rows.set(key,v);
  if(first){req.socket.destroy();return;}
  res.end(JSON.stringify({id:v.id}));
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{
  const c=new SpendingClient({CAMPAIGN_BUDGET_URL:`http://127.0.0.1:${server.address().port}`,CAMPAIGN_BUDGET_JOB:'j',CAMPAIGN_BUDGET_ARM:'kz'},{retryDelays:[1,1]});
  const id=await c.reserve('https://example.invalid',{body:JSON.stringify({model:'m',max_tokens:2})});
  await c.settle(id,{input_tokens:1,output_tokens:1});
  assert.equal(rows.size,2);assert.deepEqual(seen[0],seen[1]);assert.deepEqual(seen[2],seen[3]);
  await assert.rejects(c.call('/deny',{}),/per_task_budget_exhausted/);assert.equal(deny,1);
 }finally{await new Promise(r=>server.close(r));}
});
