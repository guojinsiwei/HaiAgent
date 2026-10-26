import http from 'node:http';
import {randomUUID} from 'node:crypto';
import {decodeSSE} from './messages-protocol.mjs';

export function totalUsage(usage) {
  if(!usage || !['input_tokens','output_tokens'].every(k=>Number.isSafeInteger(usage[k])&&usage[k]>=0))return null;
  const extra=['cache_read_input_tokens','cache_creation_input_tokens'].map(k=>usage[k]??0);
  if(!extra.every(x=>Number.isSafeInteger(x)&&x>=0))return null;
  const total=usage.input_tokens+usage.output_tokens+extra[0]+extra[1];
  return Number.isSafeInteger(total)?total:null;
}

export function usageFromSSE(text) {
  let usage={},stopped=false,started=false,finalOutput=false;
  const {events,malformed}=decodeSSE(text);
  if(malformed)return null;
  for(const data of events){
    if(!data||typeof data!=='object')return null;
    if(data.type==='ping')continue;
    if(stopped||data.type==='error')return null;
    // message_delta is cumulative, not an additional usage event.
    if(data.type==='message_start') {
      if(started)return null;started=true;
      Object.assign(usage,data.message?.usage??{});
      for(const key of ['input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens']) {
        if(usage[key]!==undefined&&(!Number.isSafeInteger(usage[key])||usage[key]<0))return null;
      }
    }
    if(data.type==='message_delta') {
      if(!started)return null;
      const next=data.usage??{};
      for(const key of ['input_tokens','output_tokens','cache_read_input_tokens','cache_creation_input_tokens']) {
        if(next[key]!==undefined&&(!Number.isSafeInteger(next[key])||next[key]<0||next[key]<(usage[key]??0)))return null;
      }
      Object.assign(usage,next);
      if(next.output_tokens!==undefined)finalOutput=true;
    }
    if(data.type==='message_stop')stopped=true;
  }
  // Initial output counts are not final usage. Never release a reservation
  // using only the start event and a stop marker from a truncated response.
  return started&&stopped&&finalOutput&&totalUsage(usage)!==null?usage:null;
}

export function costUsage(usage) {
  if(totalUsage(usage)===null)return null;
  return Math.ceil((usage.input_tokens*200+usage.output_tokens*800+(usage.cache_read_input_tokens??0)*4+(usage.cache_creation_input_tokens??0)*200)/100);
}

export class SpendingClient {
  constructor(env=process.env,{timeoutMs=35000,retryDelays=[250,1000]}={}){
    this.timeoutMs=timeoutMs;this.retryDelays=retryDelays;
    this.url=env.CAMPAIGN_BUDGET_URL;this.token=env.CAMPAIGN_BUDGET_TOKEN;
    this.job=env.CAMPAIGN_BUDGET_JOB;this.arm=env.CAMPAIGN_BUDGET_ARM;
    if(env.CAMPAIGN_BUDGET_REQUIRED==='1'&&!(this.url&&this.token&&this.job&&this.arm))throw Error('budget_configuration_missing');
  }
  async call(path,value){
    // Replay only the budget RPC with the same lease/body; never replay model calls.
    for(let attempt=0;;attempt++){
      try{return await this.callOnce(path,value);}
      catch(error){
        if(error.message!=='budget_service_unavailable'||attempt>=this.retryDelays.length)throw error;
        await new Promise(r=>setTimeout(r,this.retryDelays[attempt]));
      }
    }
  }
  callOnce(path,value){
    return new Promise((resolve,reject)=>{
      const body=JSON.stringify(value),url=new URL(path,this.url);
      if(url.protocol!=='http:')return reject(Error('invalid_budget_service_protocol'));
      const req=http.request(url,{method:'POST',headers:{'Authorization':'Bearer '+this.token,'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)}},res=>{
        let text='';res.setEncoding('utf8');
        res.on('data',chunk=>{text+=chunk;if(text.length>8192)res.destroy(Error('budget_response_too_large'));});
        res.on('error',()=>reject(Error('budget_service_unavailable')));
        res.on('end',()=>{
          try {const value=JSON.parse(text);if(res.statusCode!==200)reject(Error(value.error??'budget_service_unavailable'));else resolve(value);}
          catch{reject(Error('budget_service_unavailable'));}
        });
      });
      req.setTimeout(this.timeoutMs,()=>req.destroy());
      req.on('error',()=>reject(Error('budget_service_unavailable')));req.end(body);
    });
  }
  async reserve(endpoint,init){
    if(!this.url)return null;
    let body;try{body=JSON.parse(init?.body);}catch{throw Error('budget_request_not_json');}
    const request={id:randomUUID(),job:this.job,arm:this.arm,endpoint,model:body.model,max_tokens:body.max_tokens};
    while(true){
      if(init?.signal?.aborted)throw Error('budget_wait_aborted');
      try{return (await this.call('/reserve',request)).id;}
      catch(error){
        if(error.message==='campaign_budget_exhausted')await this.halt(error.message);
        if(error.message!=='waiting_for_inflight_usage')throw error;
        await new Promise(r=>setTimeout(r,1000));
      }
    }
  }
  async settle(id,usage){
    if(id===null)return;
    const tokens=costUsage(usage);
    const result=await this.call('/settle',{id,tokens,conservative:false});
    if(result.halt_reason)throw Error(result.halt_reason);
    if(result.task_halt_reason)throw Error(result.task_halt_reason);
  }
  async halt(reason){
    if(this.url)await this.call('/halt',{reason,job:this.job});
  }
}
