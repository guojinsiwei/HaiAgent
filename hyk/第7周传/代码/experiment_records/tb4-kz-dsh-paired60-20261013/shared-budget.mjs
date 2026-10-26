// Identical instrumentation/limits in BOTH arms; no memory or decision policy.
import { appendFileSync, writeFileSync } from 'node:fs';
import { reserveCost, settleCost } from './src/budget.mjs';
export const name='paired-budget';
export const inject=['llm','tools'];
export function apply(ctx) {
  const started=Date.now(), state={requests:0,tools:0,inputTokens:0,outputTokens:0,stopped:null};
  const c={provider:'deepseek-official',model:'deepseek-flash',limitCny:50,inputPerMillion:2,outputPerMillion:8,
    maxInputTokens:1000000,maxOutputTokens:32768,priceBasis:'historical upper estimate NOT TokenPlan invoice'};
  const dir=process.env.PAIRED_AUDIT_DIR;
  function record(event,detail={}) {
    appendFileSync(dir+'/shared.jsonl',JSON.stringify({time:new Date().toISOString(),event,...detail})+'\n');
    writeFileSync(dir+'/shared-state.json',JSON.stringify(state));
  }
  function check(kind='step') {
    const reason=state.cost?.boundExceeded?'cost_bound':Date.now()-started>=7200000?'wall':kind!=='tool'&&state.requests>=800?'requests':kind!=='request'&&state.tools>=600?'tools':null;
    if(reason){state.stopped=reason;record('budget_exhausted',{reason});throw new Error('PAIRED_BUDGET_EXHAUSTED: '+reason);}
  }
  ctx.on('agent/pre-step',async(payload,next)=>{try{check();}catch{return{kind:'reject'};}return next();});
  ctx.on('agent/request',async(payload,next)=>({...await next(),temperature:0,reasoningEffort:'off',maxTokens:32768}));
  ctx.on('llm/stream',async function*(options,next){
    check('request');let reservation;
    try{reservation=reserveCost(state,c,options);}catch(error){state.stopped='cost_or_route';record('budget_refused',{reason:'cost_or_route'});throw error;}
    state.requests++;record('request',{number:state.requests,role:options.purpose??'solver'});
    let usage=null,completed=false;
    try {for await(const chunk of next()){
      if(chunk.type==='usage')usage=chunk.usage;
      if(chunk.type==='finish')completed=['stop','tool-calls','max-tokens','length'].includes(chunk.reason?.kind);
      yield chunk;
    }} finally {
      if(usage){state.inputTokens+=usage.inputTokens??0;state.outputTokens+=usage.outputTokens??0;}
      try {settleCost(state,c,reservation,usage,completed);}
      finally {record('request_end',{completed,usage});}
    }
  });
  ctx.on('tools/pre-execute',async(exec,next)=>{try{check('tool');}catch{return{kind:'deny',reason:'Shared budget exhausted; retain artifacts.'};}return next();});
  ctx.on('tools/execute',async(exec,next)=>{check('tool');state.tools++;record('tool',{number:state.tools,name:exec.name,callId:exec.callId});return next();});
  record('budget_ready',{requests:800,tools:600,seconds:7200,costGuardEstimateCny:50});
}
