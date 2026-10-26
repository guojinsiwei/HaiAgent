import fs from 'node:fs';
import {guardedFetch} from './provider-guard.mjs';
const {key}=JSON.parse(fs.readFileSync(0,'utf8'));
const fetch=guardedFetch(globalThis.fetch,{directory:process.env.CANARY_LOG,idleTimeoutMs:45000,timeoutMs:90000,maxAttempts:1});
const response=await fetch('https://api.taotoken.net/token/v1/messages',{
 method:'POST',headers:{'content-type':'application/json','anthropic-version':'2023-06-01','x-api-key':key},
 body:JSON.stringify({model:'deepseek-flash',max_tokens:32,temperature:0,stream:true,thinking:{type:'disabled'},messages:[{role:'user',content:'Reply only OK.'}]})
});
await response.text();
console.log(JSON.stringify({passed:response.status===200,status:response.status}));
