import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {guardedFetch} from './provider-guard.mjs';
import {message,sse} from './protocol-fixtures.mjs';
const endpoint='https://api.taotoken.net/token/v1/messages';
test('missing final usage retains unknown charge, reserves anew and exposes only complete recovery',async t=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'retry-stream-'));
 t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 const order=[];let calls=0,leases=0;
 const budget={reserve:async()=>{order.push('reserve');return ++leases;},settle:async(id,usage)=>{order.push(usage===null?'unknown':'settled');if(usage===null)throw Error('usage_unavailable');}};
 const fetch=guardedFetch(async()=>sse(++calls===1?message({stop:false}):message()),{directory,budget,sleep:async()=>{}});
 assert.equal(await(await fetch(endpoint)).text(),message());
 assert.deepEqual(order,['reserve','unknown','reserve','settled']);
 assert.equal(calls,2);assert.equal(fs.existsSync(directory+'/budget-stop.json'),false);
});
test('budget refusal after missing usage prevents second provider call',async t=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'retry-stream-'));
 t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 let leases=0,calls=0;
 const budget={reserve:async()=>{if(++leases===2)throw Error('per_task_budget_exhausted');return leases;},settle:async()=>{throw Error('usage_unavailable');}};
 const fetch=guardedFetch(async()=>{calls++;return sse(message({stop:false}));},{directory,budget,sleep:async()=>{}});
 await assert.rejects(fetch(endpoint),/per_task_budget_exhausted/);assert.equal(calls,1);
});
