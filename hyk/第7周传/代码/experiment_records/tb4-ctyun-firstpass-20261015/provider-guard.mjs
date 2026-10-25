// Buffer and validate each response; never expose partial tool calls to DSH.
import fs from 'node:fs';
import {SpendingClient,usageFromSSE,totalUsage} from './spending-client.mjs';
import {decodeSSE,validateMessages} from './messages-protocol.mjs';

const safeCode=value=>String(value?.error?.code??value?.error?.type??value?.code??'').replace(/[^a-zA-Z0-9_-]/g,'').slice(0,100);
export function classify(status,value) {
  const error=value?.error??value??{},code=String(error.code??error.type??'').toUpperCase();
  if(['QUOTA','INSUFFICIENT_QUOTA','QUOTA_EXCEEDED','INSUFFICIENT_BALANCE'].includes(code)||String(error.message??'').toLowerCase().includes('no usable token plan quota'))return 'quota';
  if(['600003','CONTENT_FILTER','CONTENT_FILTERED','CONTENT_POLICY_VIOLATION'].includes(code))return 'refusal';
  if([401,402,403].includes(status))return 'credentials';
  if([408,429].includes(status)||status>=500)return 'temporary';
  if(status>=400)return 'invalid_request';
  return 'other';
}
export const completeSSE=text=>validateMessages(text).complete;

export function guardedFetch(nativeFetch,{directory,clock=Date.now,sleep=ms=>new Promise(r=>setTimeout(r,ms)),budget=new SpendingClient(),timeoutMs=180000,maxResponseBytes=16*1024*1024}) {
  let held=null,retryAt=0;
  fs.mkdirSync(directory,{recursive:true});
  const file=directory+'/provider-state.json';
  const record=event=>fs.appendFileSync(directory+'/provider-events.jsonl',JSON.stringify({time:clock()/1000,...event})+'\n');
  const save=value=>{const tmp=file+'.'+process.pid+'.tmp';fs.writeFileSync(tmp,JSON.stringify(value));fs.renameSync(tmp,file);};
  const hold=(kind,reason,extra={})=>{
    held=kind;save({kind,reason,...extra,updated_utc:new Date(clock()).toISOString()});
    fs.writeFileSync(directory+'/provider-stop.json',JSON.stringify({kind,reason}));
  };
  const stopBudget=error=>{
    // Preserve the primary provider error; accounting stop is recorded separately.
    if(!held)hold('budget',error.message);
    fs.writeFileSync(directory+'/budget-stop.json',JSON.stringify({reason:error.message}));
    throw Object.assign(Error('Campaign spending stopped: '+error.message),{code:'CAMPAIGN_BUDGET_STOP'});
  };
  const settle=async(lease,usage)=>{
    record({event:'settlement_attempt',lease,tokens:totalUsage(usage),usage_known:totalUsage(usage)!==null});
    try{await budget.settle(lease,usage);record({event:'settlement_accepted',lease});}catch(error){stopBudget(error);}
  };
  const latch=async kind=>{
    try{await budget.halt?.('provider_'+kind);}catch(error){stopBudget(error);}
  };
  const fail=async(kind,reason)=>{
    hold(kind,reason);
    await latch(kind);
    throw Object.assign(Error('Provider unavailable: '+reason),{code:'PROVIDER_UNAVAILABLE'});
  };
  return async(input,init)=>{
    const url=typeof input==='string'?input:input instanceof URL?input.href:input.url;
    if(url!==(process.env.DSH_EXPECT_ENDPOINT??'https://api.taotoken.net/token/v1/messages'))return nativeFetch(input,init);
    if(held)throw Object.assign(Error('Provider unavailable: '+held),{code:'PROVIDER_UNAVAILABLE'});
    for(let attempt=0;attempt<2;attempt++) {
      if(retryAt>clock())await sleep(retryAt-clock());
      if(held)throw Object.assign(Error('Provider unavailable: '+held),{code:'PROVIDER_UNAVAILABLE'});
      if(init?.signal?.aborted)throw init.signal.reason;
      let lease;try{lease=await budget.reserve(url,init);}catch(error){stopBudget(error);}
      record({event:'request',lease,attempt});
      let response,text;
      const controller=new AbortController();
      const abort=()=>controller.abort(init.signal.reason);
      init?.signal?.addEventListener('abort',abort,{once:true});
      const timer=setTimeout(()=>controller.abort(Error('provider_request_deadline')),timeoutMs);
      try {
        response=await nativeFetch(input,{...init,signal:controller.signal});
        const reader=response.body?.getReader(),chunks=[];let size=0;
        if(reader)while(true) {
          const {done,value}=await reader.read();if(done)break;
          size+=value.byteLength;
          if(size>maxResponseBytes){await reader.cancel();throw Error('response_size_limit');}
          chunks.push(Buffer.from(value));
        }
        text=Buffer.concat(chunks).toString('utf8');
      } catch(error) {
        record({event:'transport_error',lease,error_type:error.name});
        hold('transport','request_or_body_failed');
        await settle(lease,null);
        return fail('transport','request_or_body_failed');
      } finally {
        clearTimeout(timer);init?.signal?.removeEventListener('abort',abort);
      }
      const sse=response.headers.get('content-type')?.includes('text/event-stream');
      let value=null;try{if(!sse)value=JSON.parse(text);}catch{}
      const events=sse?decodeSSE(text).events:[];
      const streamError=events.find(e=>e?.type==='error');
      let kind=classify(response.status,streamError??value);
      if(streamError&&kind==='other')kind='invalid_request';
      const usage=sse?usageFromSSE(text):value?.usage??null;
      const validation=sse?validateMessages(text):{complete:false,reason:'expected_messages_sse'};
      record({event:'response',lease,status:response.status,kind,code:safeCode(streamError??value),complete:validation.complete,validation_reason:validation.reason});
      if(['quota','credentials','refusal','invalid_request'].includes(kind)) {
        hold(kind,'provider_'+kind,{status:response.status,code:safeCode(streamError??value)});
        await latch(kind);
        await settle(lease,usage);
        throw Object.assign(Error('Provider unavailable: '+kind),{code:'PROVIDER_UNAVAILABLE'});
      }
      await settle(lease,usage);
      if(totalUsage(usage)===null)return fail('accounting','usage_unavailable');
      if(kind==='temporary'||!validation.complete) {
        record({event:'rejected_response',lease,reason:kind==='temporary'?'temporary_http':validation.reason});
        if(attempt===1)return fail(kind==='temporary'?'temporary_exhausted':'protocol',validation.reason??'temporary_http');
        const raw=response.headers.get('retry-after'),seconds=raw===null?0:Number(raw);
        const delay=Number.isFinite(seconds)?seconds*1000:Date.parse(raw)-clock();
        if(delay>60000)return fail('temporary_exhausted','retry_after_exceeds_window');
        retryAt=clock()+Math.max(5000,Number.isFinite(delay)?delay:0);continue;
      }
      save({kind:'available'});
      const headers=new Headers(response.headers);headers.delete('content-length');headers.delete('content-encoding');
      return new Response(text,{status:response.status,statusText:response.statusText,headers});
    }
  };
}
if(process.env.PAIRED_AUDIT_DIR)globalThis.fetch=guardedFetch(globalThis.fetch,{directory:process.env.PAIRED_AUDIT_DIR});
