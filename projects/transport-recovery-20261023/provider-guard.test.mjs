import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {guardedFetch} from './provider-guard.mjs';

const endpoint='https://api.taotoken.net/token/v1/messages';
const encode=x=>new TextEncoder().encode(x);
const sse=[
 {type:'message_start',message:{id:'m',type:'message',role:'assistant',model:'deepseek-flash',content:[],stop_reason:null,usage:{input_tokens:2,output_tokens:0}}},
 {type:'content_block_start',index:0,content_block:{type:'text',text:''}},
 {type:'content_block_delta',index:0,delta:{type:'text_delta',text:'ok'}},
 {type:'content_block_stop',index:0},
 {type:'message_delta',delta:{stop_reason:'end_turn',stop_sequence:null},usage:{output_tokens:1}},
 {type:'message_stop'}
].map(x=>'event: '+x.type+'\ndata: '+JSON.stringify(x)+'\n\n').join('');
function fixture(native,options={}){
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'provider-repair-'));
 const leases=[],settled=[],halts=[];
 const budget={reserve:async()=>{const id=String(leases.length);leases.push(id);return id;},
   settle:async(id,u)=>{settled.push({id,u});if(u===null)throw Error('usage_unavailable');},halt:async reason=>halts.push(reason)};
 const fetch=guardedFetch(native,{directory,budget,sleep:async()=>{},...options});
 return{fetch,leases,settled,halts,directory,close(){fs.rmSync(directory,{recursive:true,force:true});}};
}
const ok=()=>new Response(sse,{headers:{'content-type':'text/event-stream'}});
test('independent requests each recover; uncertain leases are retained',async()=>{
 let n=0;const f=fixture(async()=>{if(n++%2===0)throw Object.assign(Error('network'),{code:'ECONNRESET'});return ok();});
 try{for(let i=0;i<3;i++)assert.equal(await(await f.fetch(endpoint,{})).text(),sse);
 assert.equal(f.leases.length,6);assert.equal(f.settled.filter(x=>x.u===null).length,3);assert.equal(f.halts.length,3);
 assert.equal(fs.existsSync(path.join(f.directory,'provider-stop.json')),false);}finally{f.close();}
});
test('total outage has a finite attempt count and latches before accounting stop',async()=>{
 const f=fixture(async()=>{throw Error('unreachable');});
 try{await assert.rejects(f.fetch(endpoint,{}),/Provider unavailable/);assert.equal(f.leases.length,3);
 assert.equal(f.settled.length,3);assert.equal(JSON.parse(fs.readFileSync(path.join(f.directory,'provider-stop.json'))).kind,'transport');
 await assert.rejects(f.fetch(endpoint,{}));assert.equal(f.leases.length,3);}finally{f.close();}
});
test('completed SSE does not wait for connection close',async()=>{
 const f=fixture(async()=>new Response(new ReadableStream({start(c){c.enqueue(encode(sse));}}),{headers:{'content-type':'text/event-stream'}}),{idleTimeoutMs:20});
 try{assert.equal(await(await f.fetch(endpoint,{})).text(),sse);assert.equal(f.leases.length,1);}finally{f.close();}
});
test('partial body is never exposed and stalled reader is bounded',async()=>{
 let n=0;const f=fixture(async()=>++n===1?new Response(new ReadableStream({start(c){c.enqueue(encode('event: message_start\ndata: {}\n\n'));}}),{headers:{'content-type':'text/event-stream'}}):ok(),{idleTimeoutMs:10});
 try{assert.equal(await(await f.fetch(endpoint,{})).text(),sse);assert.equal(f.settled[0].u,null);}finally{f.close();}
});
test('final message_stop without a blank line is framed for the real SSE consumer',async()=>{
 const f=fixture(async()=>new Response(sse.trimEnd(),{headers:{'content-type':'text/event-stream'}}));
 try{const text=await(await f.fetch(endpoint,{})).text();assert.ok(text.endsWith('\n\n'));assert.equal(text,sse);}finally{f.close();}
});
test('credentials do not trigger paid retries',async()=>{
 const f=fixture(async()=>new Response(JSON.stringify({error:{type:'authentication_error'}}),{status:401}));
 try{await assert.rejects(f.fetch(endpoint,{}));assert.equal(f.leases.length,1);assert.equal(f.halts[0],'provider_credentials');}finally{f.close();}
});
