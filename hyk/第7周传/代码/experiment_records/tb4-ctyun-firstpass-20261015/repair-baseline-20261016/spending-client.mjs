import http from 'node:http';
import {randomUUID} from 'node:crypto';

export function totalUsage(usage) {
  if(!usage || !['input_tokens','output_tokens'].every(k=>Number.isSafeInteger(usage[k])&&usage[k]>=0))return null;
  const extra=['cache_read_input_tokens','cache_creation_input_tokens'].map(k=>usage[k]??0);
  if(!extra.every(x=>Number.isSafeInteger(x)&&x>=0))return null;
  return usage.input_tokens+usage.output_tokens+extra[0]+extra[1];
}

export function usageFromSSE(text) {
  let usage={},stopped=false;
  for(const line of text.split(/\r?\n/)){
    if(!line.startsWith('data:'))continue;
    let data;try{data=JSON.parse(line.slice(5));}catch{continue;}
    // message_delta is cumulative, not an additional usage event.
    if(data.type==='message_start')Object.assign(usage,data.message?.usage??{});
    if(data.type==='message_delta')Object.assign(usage,data.usage??{});
    if(data.type==='message_stop')stopped=true;
  }
  return stopped&&totalUsage(usage)!==null?usage:null;
}

export class SpendingClient {
  constructor(env=process.env){
    this.url=env.CAMPAIGN_BUDGET_URL;this.token=env.CAMPAIGN_BUDGET_TOKEN;
    this.job=env.CAMPAIGN_BUDGET_JOB;this.arm=env.CAMPAIGN_BUDGET_ARM;
    if(env.CAMPAIGN_BUDGET_REQUIRED==='1'&&!(this.url&&this.token&&this.job&&this.arm))throw Error('budget_configuration_missing');
  }
  call(path,value){
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
      req.setTimeout(10000,()=>req.destroy());
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
      catch(error){if(error.message!=='waiting_for_inflight_usage')throw error;await new Promise(r=>setTimeout(r,1000));}
    }
  }
  async settle(id,usage){
    if(id===null)return;
    const tokens=totalUsage(usage);
    const result=await this.call('/settle',{id,tokens,conservative:tokens===null});
    if(result.halt_reason)throw Error(result.halt_reason);
  }
}
