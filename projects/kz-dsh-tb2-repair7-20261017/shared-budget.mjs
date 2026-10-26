// Includes Solver, KZ roles and native compaction. Actual HTTP retries are also
// admitted separately by the campaign ledger before network transmission.
import {appendFileSync,writeFileSync,renameSync} from 'node:fs';
export const name='paired-budget';
export const inject=['llm','tools'];
export function apply(ctx) {
  const state={requests:0,tools:0,inputTokens:0,outputTokens:0,cacheReadTokens:0,cacheWriteTokens:0,unknownUsageRequests:0,stopped:null,budgetMode:'bounded_peak_price_estimate'};
  const dir=process.env.PAIRED_AUDIT_DIR;
  function record(event,detail={}) {
    const time=new Date().toISOString();state.updated_utc=time;
    appendFileSync(dir+'/shared.jsonl',JSON.stringify({time,event,...detail})+'\n');
    writeFileSync(dir+'/shared-state.json.tmp',JSON.stringify(state));renameSync(dir+'/shared-state.json.tmp',dir+'/shared-state.json');
  }
  function stop(reason) {
    state.stopped=reason;record('limit_stop',{reason});writeFileSync(dir+'/limit-stop.json',JSON.stringify({reason}));throw Error(reason);
  }
  ctx.on('agent/request',async(payload,next)=>({...await next(),temperature:0,reasoningEffort:'off',maxTokens:16384}));
  ctx.on('llm/stream',async function*(options,next){
    if(state.stopped)throw Error(state.stopped);
    if(state.requests>=120)stop('per_task_request_limit');
    state.requests++;record('request',{number:state.requests,role:options.sessionId?.includes(':kz:')?options.sessionId.split(':').at(-2):options.purpose??'solver'});
    let usage=null,completed=false;
    try {for await(const chunk of next()) {
      if(chunk.type==='usage')usage=chunk.usage;
      if(chunk.type==='finish')completed=['stop','tool-calls','max-tokens','length'].includes(chunk.reason?.kind);
      yield chunk;
    }} finally {
      if(usage)for(const k of ['inputTokens','outputTokens','cacheReadTokens','cacheWriteTokens'])state[k]+=usage[k]??0;
      else state.unknownUsageRequests++;
      record('request_end',{completed,usage});
    }
  });
  ctx.on('tools/execute',async(exec,next)=>{
    if(state.stopped)throw Error(state.stopped);
    if(state.tools>=180)stop('per_task_tool_limit');
    state.tools++;record('tool',{number:state.tools,name:exec.name,callId:exec.callId});
    try{return await next();}finally{record('tool_end',{callId:exec.callId});}
  });
  record('budget_ready',{requests:120,tools:180,seconds:2700,estimatePeakCny:4});
}
