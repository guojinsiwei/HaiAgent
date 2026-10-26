import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {guardedFetch,completeSSE} from './provider-guard.mjs';
import {message,sse,frame} from './protocol-fixtures.mjs';
const endpoint='https://api.taotoken.net/token/v1/messages';
function setup(t,fn,options={}) {
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'provider-fixture-'));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  let now=0,leases=0;const sleeps=[],settlements=[],halts=[];
  const budget={reserve:async()=>++leases,settle:async(id,usage)=>settlements.push({id,usage}),halt:async reason=>halts.push(reason)};
  return {directory,sleeps,settlements,halts,fetch:guardedFetch(fn,{directory,budget,clock:()=>now,sleep:async ms=>{sleeps.push(ms);now+=ms;},...options})};
}

test('only complete blocks, stop reason and tool JSON reach the harness',()=>{
  assert.equal(completeSSE(message()),true);assert.equal(completeSSE(message({tool:true})),true);
  for(const options of [{reason:false},{closed:false},{stop:false},{tool:true,json:'{"x":'},{tool:true,json:'[]'}])assert.equal(completeSSE(message(options)),false);
  assert.equal(completeSSE('data: {"type":"message_stop"}\n\n'),false);
});

test('missing reason with final usage retries once before returning any content',async t=>{
  let calls=0;const s=setup(t,async()=>sse(++calls===1?message({reason:false}):message()));
  assert.equal(await(await s.fetch(endpoint)).text(),message());assert.equal(calls,2);
  assert.deepEqual(s.settlements.map(x=>x.id),[1,2]);assert.deepEqual(s.halts,[]);
});

test('unclosed tool block never reaches a solver',async t=>{
  let calls=0;const s=setup(t,async()=>{calls++;return sse(message({tool:true,closed:false}));});
  await assert.rejects(()=>s.fetch(endpoint),/unavailable/);
  await assert.rejects(()=>s.fetch(endpoint),/unavailable/);
  assert.equal(calls,2);assert.deepEqual(s.halts,['provider_protocol']);
});

test('unknown usage stops after one request without freeing its maximum',async t=>{
  let calls=0;const s=setup(t,async()=>{calls++;return sse(message({stop:false}));});
  await assert.rejects(()=>s.fetch(endpoint),/usage_unavailable/);
  await assert.rejects(()=>s.fetch(endpoint),/unavailable/);
  assert.equal(calls,1);assert.equal(s.settlements[0].usage,null);
});

test('provider refusal is latched across HTTP and SSE, without content logging',async t=>{
  for(const wire of ['http','sse']) {
    let calls=0;const error={error:{code:'600003',message:'private fixture refusal'}};
    const s=setup(t,async()=>{calls++;return wire==='http'?Response.json(error,{status:400}):sse(frame([{type:'error',...error}]));});
    await assert.rejects(()=>s.fetch(endpoint),/unavailable/);await assert.rejects(()=>s.fetch(endpoint),/unavailable/);
    assert.equal(calls,1);assert.deepEqual(s.halts,['provider_refusal']);
    assert.equal(JSON.parse(fs.readFileSync(s.directory+'/provider-state.json')).kind,'refusal');
    assert.ok(!fs.readFileSync(s.directory+'/provider-events.jsonl','utf8').includes('private fixture'));
  }
});

test('quota and credential errors halt shared admission immediately',async t=>{
  for(const [status,code,kind] of [[429,'QUOTA','quota'],[403,'unauthorized','credentials'],[400,'bad_input','invalid_request']]) {
    const s=setup(t,async()=>Response.json({error:{code}},{status}));
    await assert.rejects(()=>s.fetch(endpoint),/unavailable/);assert.deepEqual(s.halts,['provider_'+kind]);
  }
});

test('temporary 429 retries only when usage is known and honors Retry-After',async t=>{
  let calls=0;const s=setup(t,async()=>++calls===1?Response.json({usage:{input_tokens:0,output_tokens:0}},{status:429,headers:{'retry-after':'12'}}):sse(message()));
  assert.ok(completeSSE(await(await s.fetch(endpoint)).text()));assert.equal(calls,2);assert.deepEqual(s.sleeps,[12000]);
});

test('temporary errors with unknown usage do not trigger paid retries',async t=>{
  let calls=0;const s=setup(t,async()=>{calls++;return Response.json({error:{}},{status:503});});
  await assert.rejects(()=>s.fetch(endpoint),/usage_unavailable/);assert.equal(calls,1);
});

test('long Retry-After holds instead of retrying prematurely',async t=>{
  const s=setup(t,async()=>Response.json({usage:{input_tokens:0,output_tokens:0}},{status:429,headers:{'retry-after':'120'}}));
  await assert.rejects(()=>s.fetch(endpoint),/retry_after/);assert.deepEqual(s.sleeps,[]);
});

test('real HTTP stream stalls are bounded, accounted once and latched',async t=>{
  const http=await import('node:http');
  const server=http.createServer((req,res)=>{res.writeHead(200,{'content-type':'text/event-stream'});res.write('data: ');});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const previous=process.env.DSH_EXPECT_ENDPOINT;
  const url='http://127.0.0.1:'+server.address().port+'/v1/messages';process.env.DSH_EXPECT_ENDPOINT=url;
  try {
    const s=setup(t,fetch,{timeoutMs:100});
    await assert.rejects(()=>s.fetch(url),/unavailable/);
    assert.equal(s.settlements.length,1);assert.equal(s.settlements[0].usage,null);
    assert.deepEqual(s.halts,['provider_transport']);
  } finally {
    if(previous===undefined)delete process.env.DSH_EXPECT_ENDPOINT;else process.env.DSH_EXPECT_ENDPOINT=previous;
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
  }
});

test('oversize response is bounded and does not leak into solver',async t=>{
  const s=setup(t,async()=>sse(message()),{maxResponseBytes:20});
  await assert.rejects(()=>s.fetch(endpoint),/unavailable/);assert.equal(s.settlements[0].usage,null);
});

test('replayed body drops stale compression and content length headers',async t=>{
  const s=setup(t,async()=>new Response(message(),{headers:{'content-type':'text/event-stream','content-encoding':'gzip','content-length':'1'}}));
  const res=await s.fetch(endpoint);assert.equal(res.headers.get('content-encoding'),null);assert.equal(res.headers.get('content-length'),null);
  assert.equal(await res.text(),message());
});
