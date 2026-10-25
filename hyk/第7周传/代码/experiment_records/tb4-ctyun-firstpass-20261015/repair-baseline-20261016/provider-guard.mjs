// Availability and complete SSE delivery. Does not change prompts or tool actions.
import fs from 'node:fs';
import {SpendingClient,usageFromSSE} from './spending-client.mjs';
export function classify(status, value) {
  const error=value?.error??value??{},code=String(error.code??error.type??'').toUpperCase();
  if(['QUOTA','INSUFFICIENT_QUOTA','QUOTA_EXCEEDED','INSUFFICIENT_BALANCE'].includes(code)||String(error.message??'').toLowerCase().includes('no usable token plan quota'))return 'quota';
  if([401,402,403].includes(status))return 'credentials';
  if([408,429].includes(status)||status>=500)return 'temporary';
  return 'other';
}
export function completeSSE(text) {
  return text.split(/\r?\n/).some(line=>{
    if(!line.startsWith('data:'))return false;
    try{return JSON.parse(line.slice(5)).type==='message_stop';}catch{return false;}
  });
}
export function guardedFetch(nativeFetch,{directory,clock=Date.now,sleep=ms=>new Promise(r=>setTimeout(r,ms)),budget=new SpendingClient()}) {
  let held=null,retryAt=0,failures=0;
  fs.mkdirSync(directory,{recursive:true});
  const file=directory+'/provider-state.json';
  const record=event=>fs.appendFileSync(directory+'/provider-events.jsonl',JSON.stringify({time:clock()/1000,...event})+'\n');
  const save=value=>{const tmp=file+'.'+process.pid+'.tmp';fs.writeFileSync(tmp,JSON.stringify(value));fs.renameSync(tmp,file);};
  const stopBudget=error=>{
    held='budget';save({kind:'budget',reason:error.message,updated_utc:new Date(clock()).toISOString()});
    fs.writeFileSync(directory+'/budget-stop.json',JSON.stringify({reason:error.message}));
    throw Object.assign(Error('Campaign spending stopped: '+error.message),{code:'CAMPAIGN_BUDGET_STOP'});
  };
  const settle=async(lease,usage)=>{try{await budget.settle(lease,usage);}catch(error){stopBudget(error);}};
  return async(input,init)=>{
    const url=typeof input==='string'?input:input instanceof URL?input.href:input.url;
    if(url!==(process.env.DSH_EXPECT_ENDPOINT??'https://api.taotoken.net/token/v1/messages'))return nativeFetch(input,init);
    if(held)throw Object.assign(Error('Provider unavailable: '+held),{code:'PROVIDER_UNAVAILABLE'});
    for(let attempt=0;attempt<2;attempt++){
      const delay=retryAt-clock();if(delay>0)await sleep(delay);
      if(held)throw Object.assign(Error('Provider unavailable: '+held),{code:'PROVIDER_UNAVAILABLE'});
      if(init?.signal?.aborted)throw init.signal.reason;
      let lease;try{lease=await budget.reserve(url,init);}catch(error){stopBudget(error);}
      record({event:'request'});
      let response;
      try{response=await nativeFetch(input,init);}catch(error){
        await settle(lease,null);
        record({event:'transport_error',error_type:error.name});
        retryAt=clock()+Math.min(60000,5000*2**Math.min(failures++,4));
        if(attempt===1)throw error;continue;
      }
      let value=null;
      if(!response.ok){try{value=await response.clone().json();}catch{}}
      const kind=classify(response.status,value);record({event:'response',status:response.status,kind});
      if(!response.ok){
        record({event:'http_error',status:response.status,code:String(value?.error?.code??value?.error?.type??'').replace(/[^a-zA-Z0-9_-]/g,'').slice(0,100)});
        await settle(lease,value?.usage??null);
      }
      if(['quota','credentials'].includes(kind)){
        held=kind;save({kind,status:response.status,updated_utc:new Date(clock()).toISOString()});return response;
      }
      if(kind==='temporary'){
        const header=response.headers.get('retry-after');
        const seconds=header===null?0:Number(header);
        const explicit=Number.isFinite(seconds)?seconds*1000:Math.max(0,Date.parse(header)-clock())||0;
        retryAt=clock()+Math.max(explicit,Math.min(60000,5000*2**Math.min(failures++,4)));
        save({kind,retry_at:retryAt/1000,status:response.status});
        if(attempt===1)return response;
        await response.body?.cancel();continue;
      }
      if(response.ok&&response.headers.get('content-type')?.includes('text/event-stream')){
        let text;
        try{text=await response.text();}catch(error){
          await settle(lease,null);
          record({event:'incomplete_stream',error_type:error.name});
          if(attempt===1)throw error;retryAt=clock()+5000;continue;
        }
        const usage=usageFromSSE(text);
        if(!usage){
          const events=[];
          for(const line of text.split(/\r?\n/))if(line.startsWith('data:')){
            try{const e=JSON.parse(line.slice(5));events.push({type:String(e.type??'').slice(0,60),usage:e.usage??e.message?.usage,error_code:String(e.error?.code??e.error?.type??'').replace(/[^a-zA-Z0-9_-]/g,'').slice(0,100)});}catch{}
          }
          record({event:'conservative_maximum_charge',complete:completeSSE(text),events:events.filter(e=>e.usage||e.type==='error'||e.type==='message_stop')});
        }
        await settle(lease,usage);
        for(const line of text.split(/\r?\n/)){
          if(!line.startsWith('data:'))continue;
          let data;try{data=JSON.parse(line.slice(5));}catch{continue;}
          if(data.type==='error'&&['quota','credentials'].includes(classify(429,data))){
            held=classify(429,data);save({kind:held,status:response.status,updated_utc:new Date(clock()).toISOString()});
            throw Object.assign(Error('Provider unavailable: '+held),{code:'PROVIDER_UNAVAILABLE'});
          }
        }
        if(!completeSSE(text)){
          record({event:'incomplete_stream'});
          if(attempt===1)throw Object.assign(Error('Provider stream ended before message_stop'),{code:'STREAM_CLOSED'});
          retryAt=clock()+5000;continue;
        }
        // No incomplete tool-call fragment reaches the harness, so this retry
        // cannot repeat an already executed tool. Both HTTP attempts are counted.
        failures=0;save({kind:'available'});
        return new Response(text,{status:response.status,statusText:response.statusText,headers:response.headers});
      }
      if(response.ok){let value;try{value=await response.clone().json();}catch{}await settle(lease,value?.usage??null);}
      if(response.ok){failures=0;save({kind:'available'});}
      return response;
    }
  };
}
if(process.env.PAIRED_AUDIT_DIR)globalThis.fetch=guardedFetch(globalThis.fetch,{directory:process.env.PAIRED_AUDIT_DIR});
