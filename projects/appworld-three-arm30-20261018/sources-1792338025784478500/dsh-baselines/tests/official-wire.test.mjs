import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {DeepSeekAdapter,DeepSeekFileStore,resolveAdapterOptions} from '@deepseek-ai/dsh-llm-deepseek';
import {fixture} from './fixture.mjs';
import path from 'node:path';

test('official DeepSeek transport serializes requests and parses local SSE, without real credentials',{timeout:30000},async t=>{
  const received=[];
  const server=createServer(async(req,res)=>{
    let body='';for await(const b of req)body+=b;
    received.push(JSON.parse(body));
    res.writeHead(200,{'content-type':'text/event-stream'});
    const send=(type,value)=>res.write(`event: ${type}\ndata: ${JSON.stringify({type,...value})}\n\n`);
    send('message_start',{message:{id:'offline',type:'message',role:'assistant',model:'deepseek-flash',content:[],stop_reason:null,usage:{input_tokens:17,output_tokens:0}}});
    send('content_block_start',{index:0,content_block:{type:'text',text:''}});
    send('content_block_delta',{index:0,delta:{type:'text_delta',text:'Offline official transport response.'}});
    send('content_block_stop',{index:0});
    send('message_delta',{delta:{stop_reason:'end_turn',stop_sequence:null},usage:{output_tokens:7}});
    send('message_stop',{});res.end();
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));t.after(()=>new Promise(r=>server.close(r)));
  const f=await fixture(t,'native',()=>{throw new Error('scripted adapter must not be used');});
  const options=resolveAdapterOptions({baseURL:`http://127.0.0.1:${server.address().port}`,thinking:'disabled',maxTokens:32768});
  const adapter=new DeepSeekAdapter({options:()=>options,
    resolveAuth:async()=>({headers:{'x-api-key':'offline-fixture-not-a-credential'}}),resolveUserId:()=> 'offline',
    resolveFiles:()=>new DeepSeekFileStore(path.join(f.dir,'files.json')),
    prepareExtensions:async()=>({fields:{},accept:async()=>{}})});
  f.ctx.llm.registerAdapter(['official-fixture'],adapter);
  f.config.route.provider='official-fixture';f.config.route.model='deepseek-flash';
  await f.run();
  assert.equal(f.errors.length,0,String(f.errors[0]));assert.equal(received.length,1);
  assert.equal(received[0].model,'deepseek-flash');assert.equal(received[0].max_tokens,32768);
  assert.equal(f.api.state.usage.httpRequests,1);assert.equal(f.api.state.usage.inputTokens,17);assert.equal(f.api.state.usage.outputTokens,7);
});
