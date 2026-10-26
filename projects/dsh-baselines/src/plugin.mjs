import { appendFileSync, mkdirSync, writeFileSync, existsSync, realpathSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { scopeOf } from '@deepseek-ai/dsh-scope';
import { Bridge } from './bridge.mjs';
import { installTransport, requestScope } from './transport.mjs';

export const name='dsh-baseline-control';
export const inject=['tools','systemPrompt','llm'];
export const apply=(ctx,config)=>applyBaseline(ctx,{...config,algorithm:'native'});
const text=t=>({type:'text',text:t});
const notice=t=>createUserMessage({content:[text(t)],source:{kind:'baseline-state',form:'notice',summary:'Task-local algorithm state'}});
const metadata=n=>n.startsWith('recuris_')||n.startsWith('taco_');

export function applyBaseline(ctx,c) {
  if(!c.instruction||!c.workspace||!c.auditDir||!c.route?.provider||!c.route?.model)throw new Error('Explicit task, isolated workspace, audit directory and common model route required');
  const workspace=realpathSync(c.workspace); mkdirSync(c.auditDir,{recursive:true});
  const auditDir=realpathSync(c.auditDir);
  const rel=path.relative(workspace,auditDir);
  if(!rel.startsWith('..'+path.sep)&&rel!=='..'&&!path.isAbsolute(rel))throw new Error('Audit must be outside solver workspace');
  const marker=path.join(auditDir,'run.json');
  if(existsSync(marker))throw new Error('Fresh per-task audit directory required; implicit memory resume forbidden');
  writeFileSync(marker,JSON.stringify({...c,worker:c.worker?.href},null,2));
  const log=path.join(auditDir,'events.jsonl');
  const state={algorithm:c.algorithm,session:null,initialized:c.algorithm==='native',panel:null,
    status:'running',faults:[],usage:{streams:0,httpRequests:0,inputTokens:0,outputTokens:0,unknownUsage:0,nativeTools:0,metadataTools:0,roles:{}}};
  let agent=null, worker=null, signal=null, roleSerial=0, evidenceSerial=0, pendingFeedback=null;
  const started=Date.now(), verifyCalls=new Map(), projected=new Map();
  function audit(event,detail={}) {
    if(event==='auxiliary_failure_fallback'||event==='compression_fallback'||(event==='taco_log_plan_response'&&detail.kwargs?.used_fallback)||(event==='algorithm_diagnostic'&&detail.engineering_problem)) {
      state.faults.push({op:event,detail});
      if(state.status==='running')state.status='degraded_engineering_error';
    }
    appendFileSync(log,JSON.stringify({time:new Date().toISOString(),session:state.session,event,...detail})+'\n');
    writeFileSync(path.join(auditDir,'state.json'),JSON.stringify(state,null,2));
  }
  function wall(){if((Date.now()-started)/1000>c.budget.wallSeconds)throw new Error('Shared wall budget exhausted');}
  function fault(op,e){state.faults.push({op,message:e.message});state.status='engineering_error';audit('engineering_error',{op,message:e.message});}
  async function ask(m) {
    let output='',usage={},finished=false;
    for await(const chunk of ctx.llm.stream({...c.route,sessionId:state.session,purpose:m.role,
      system:m.system,messages:[{role:'user',content:[text(JSON.stringify(m.payload))]}],tools:[],signal})) {
      if(chunk.type==='block-end'&&chunk.block.type==='text')output+=chunk.block.text;
      if(chunk.type==='usage')usage={prompt_tokens:chunk.usage.inputTokens??0,completion_tokens:chunk.usage.outputTokens??0};
      if(chunk.type==='finish'){if(chunk.reason.kind!=='stop')throw new Error(`auxiliary ${m.role}: ${chunk.reason.kind}`);finished=true;}
    }
    if(!finished)throw new Error('auxiliary stream missing finish');
    audit('role_response',{role:m.role,output});return {text:output,usage};
  }
  async function call(op,payload={}) {
    try {const result=await worker.call(op,payload);audit('algorithm_operation',{op,result});return result;}
    catch(e){fault(op,e);throw e;}
  }
  function bind(a) {
    if(agent&&agent!==a)throw new Error('One task/session per DSH process is required');
    if(path.resolve(a.session.header?.cwd??workspace)!==workspace)throw new Error('Session workspace mismatch');
    if(agent)return;
    agent=a;state.session=a.session.id;
    if(c.algorithm!=='native') {
      worker=new Bridge(c.python,fileURLToPath(c.worker),ask,audit);
    }
    // Only TACO's presentation is changed; original definitions, execution,
    // schema, permission hooks and immutable result values stay with DSH.
    if(c.algorithm==='taco')for(const toolName of ['bash','job_output']) {
      const original=ctx.tools.get(toolName,a);
      if(!original)continue;
      a.ctx.tools.register({...original,finalizeContent(exec,result){
        const compressed=projected.get(exec.callId);projected.delete(exec.callId);
        return compressed??original.finalizeContent?.(exec,result)??result.content;
      }});
    }
    audit('session_bound',{workspace});
  }
  ctx.effect(()=>()=>worker?.close());
  installTransport();
  ctx.on('agent/created',({agent:a})=>bind(a));
  ctx.on('agent/error',({error})=>fault('dsh_host',error instanceof Error?error:new Error(String(error))));
  ctx.on('agent/request',async(payload,next)=>({...await next(),...c.route}));
  ctx.on('llm/stream',async function*(options,next){
    wall();
    if(options.provider!==c.route.provider||options.model!==c.route.model)throw new Error('Shared route mismatch');
    const role=options.purpose??'solver';
    state.usage.streams++;state.usage.roles[role]??={streams:0,httpRequests:0};state.usage.roles[role].streams++;
    const scope={offline:c.offline!==false,admitHttp(detail){
      wall();if(state.usage.httpRequests>=c.budget.apiRequests)throw new Error('Shared actual API request budget exhausted');
      state.usage.httpRequests++;state.usage.roles[role].httpRequests++;
      audit('http_request',{role,...detail,attempt:state.usage.httpRequests});
    }};
    const iterator=requestScope.run(scope,()=>next()[Symbol.asyncIterator]());
    let usage=null;const blocks=[];
    audit('llm_stream_start',{role,number:state.usage.streams});
    try {
      while(true){const n=await requestScope.run(scope,()=>iterator.next());if(n.done)break;
        const chunk=n.value;
        if(chunk.type==='usage')usage=chunk.usage;
        if(chunk.type==='block-end')blocks.push(chunk.block);
        yield chunk;
      }
      if(role==='solver'&&c.algorithm==='taco')pendingFeedback={
        response:blocks.filter(b=>b.type==='text').map(b=>b.text).join('\n'),
        analysis:blocks.filter(b=>b.type==='text').map(b=>b.text).join('\n'),
        commands:blocks.filter(b=>b.type==='tool-call'&&b.name==='bash').map(b=>{try{return JSON.parse(b.arguments).command??'';}catch{return '';}})};
    } finally {
      if(usage){state.usage.inputTokens+=usage.inputTokens??0;state.usage.outputTokens+=usage.outputTokens??0;}
      else state.usage.unknownUsage++;
      audit('llm_stream_end',{role,usage});
      await requestScope.run(scope,()=>iterator.return?.());
    }
  });
  async function feedback(extra={}) {
    if(c.algorithm!=='taco'||!state.initialized)return null;
    const pending=pendingFeedback;pendingFeedback=null;
    if(!pending&&!extra.feedback)return null;
    const result=await call('feedback',{...pending,...extra});state.panel=result.state;
    return result.restored;
  }
  ctx.systemPrompt.section({name:'baseline:contract',order:10300,interpolate:false,text:
    c.algorithm==='recuris'?'Recuris frozen E/W/rho/C adaptation. Use native DSH tools. Working memory is the sole goal list. recuris_verify executes the selected goal public check through native bash. Completion requires actual current verification receipts. No strategy declaration is required. Skills are fallible procedures. Use recuris_stop to report inability without claiming completion.':
    c.algorithm==='taco'?'TACO filters terminal observations. Use taco_feedback with feedback="need_full_output" when compression hid needed information. The tool restores the retained raw observation and triggers rule repair. This is not task failure feedback. Use native DSH tools to solve the task.':''});
  // Runtime memory contains literal source code (Go/Jinja double braces, etc.).
  // DSH substitutes variable values once, without parsing their contents again.
  ctx.systemPrompt.variable('baseline_memory_literal',({scope})=>agent&&scope===scopeOf(agent.ctx)?panel():'');
  ctx.systemPrompt.context({name:'baseline:memory',order:20000,text:'{{baseline_memory_literal}}'});
  function panel(){return c.algorithm==='recuris'?JSON.stringify({task:c.instruction,state:state.panel,faults:state.faults}):'';}
  ctx.on('agent/pre-step',async(payload,next)=>{
    const decision=await next();if(decision.kind==='reject')return decision;
    bind(payload.agent);signal=payload.signal;wall();
    if(!state.initialized){state.panel=await call('init',{instruction:c.instruction,environment:`DSH workspace: ${workspace}. Native tools, permissions and task-local sessions apply.`});state.initialized=true;}
    if(c.algorithm==='recuris')state.panel=await call('step');
    const fresh=panel();audit('pre_step_state',{panel:state.panel});
    return fresh?{...decision,messages:[...decision.messages,notice(fresh)]}:decision;
  });
  ctx.on('tools/pre-execute',async(exec,next)=>{
    const decision=await next();if(decision.kind!=='allow')return decision;
    wall();
    if(state.usage.nativeTools+state.usage.metadataTools>=c.budget.tools)return {kind:'deny',reason:'Shared tool budget exhausted'};
    if(c.algorithm==='taco'&&!metadata(exec.name)) {
      const restored=await feedback();
      if(restored!==null)return {kind:'deny',reason:'TACO restored the prior raw observation; reconsider this unexecuted action.\n'+restored};
    }
    return decision;
  });
  ctx.on('tools/execute',async(exec,next)=>{
    bind(exec.agent);signal=exec.signal;wall();
    if(state.usage.nativeTools+state.usage.metadataTools>=c.budget.tools)throw new Error('Shared tool budget exhausted');
    state.usage[metadata(exec.name)?'metadataTools':'nativeTools']++;
    audit('tool_dispatch',{name:exec.name,callId:exec.callId,arguments:exec.arguments});
    const result=await next();
    if(metadata(exec.name))return result;
    const id=`E${++evidenceSerial}`;const raw=(result.content??[]).filter(b=>b.type==='text').map(b=>b.text).join('\n');
    const v=result.value;
    const complete=!result.isError&&v?.kind==='foreground'&&!v.timedOut&&!v.aborted&&!v.signal&&!v.stdout?.truncated&&!v.stderr?.truncated;
    const verified=verifyCalls.get(exec.callId);
    const receipt={id,kind:verified?'verification':'observation',goal_id:verified?.goal.id??'',
      verification_digest:verified?.digest??'',output:raw,completed:complete,
      exit_code:complete?v.exitCode:null,synthetic:false,
      tool:exec.name,arguments:exec.arguments,call_id:exec.callId};
    writeFileSync(path.join(auditDir,`${id}.json`),JSON.stringify({receipt,result},null,2));
    audit('tool_observation',{id,callId:exec.callId,isError:result.isError,complete});
    if(c.algorithm==='recuris') {
      try {state.panel=await call('observe',{receipt,action:{tool:exec.name,arguments:exec.arguments},
        mutation:!verified&&!['read','glob','grep','job_output','job_list'].includes(exec.name)});}
      catch(e){return {...result,additionalContexts:[...(result.additionalContexts??[]),notice('Recuris state update failed: '+e.message)]};}
    }
    if(c.algorithm==='taco'&&['bash','job_output'].includes(exec.name)&&!result.isError) {
      const result2=await call('compress',{raw,command:exec.arguments.command??'',
        unsafe:!complete||v.exitCode!==0||v.stdout?.truncated||v.stderr?.truncated});
      state.panel=result2.state;
      if(result2.output!==raw)projected.set(exec.callId,[text(`[TACO observation ${id}; original retained in task audit]\n${result2.output}`)]);
      audit('observation_projection',{id,rawChars:raw.length,projectedChars:result2.output.length,applied:result2.applied});
    }
    return result;
  });
  ctx.on('tools/result',(exec,result)=>{if(result.isError)audit('tool_error',{callId:exec.callId,name:exec.name,error:result.error});});
  function register(toolName,description,properties,required,execute) {
    ctx.tools.register({name:toolName,description,parameters:{type:'object',properties,required,additionalProperties:false},
      output:{schema:{type:'object',additionalProperties:true},render:(_a,v)=>[text(JSON.stringify(v))]},isConcurrencySafe:()=>false,execute});
  }
  let stopped=false;
  if(c.algorithm==='recuris') {
    register('recuris_verify','Execute the current public verification for a working-memory goal through DSH bash.',{goal_id:{type:'string'}},['goal_id'],async(args,exec)=>{
      const binding=await call('verification',args);const callId=`recuris-check-${++roleSerial}`;verifyCalls.set(callId,binding);
      try {
        const result=await ctx.tools.execute({name:'bash',arguments:{command:binding.goal.verification.command,description:`Verify ${args.goal_id}`,timeoutMs:c.commandTimeoutMs},callId,agent:exec.agent,signal:exec.signal});
        return {isError:result.isError,result:result.isError?result.error:result.value,state:state.panel};
      } finally {verifyCalls.delete(callId);}
    });
    register('recuris_stop','Report incomplete work without claiming verified completion.',{reason:{type:'string'}},['reason'],async(args)=>{stopped=true;state.status=state.faults.length?'incomplete_engineering_error':'incomplete';audit('incomplete_stop',args);return {incomplete:true};});
  }
  if(c.algorithm==='taco')register('taco_feedback','Restore the previous raw observation and repair compression rules when information was lost.',{feedback:{type:'string',enum:['need_full_output']}},['feedback'],async(args)=>({raw:await feedback(args)}));
  ctx.on('agent/turn-stopping',async({agent:a,signal:s})=>{
    signal=s;
    if(c.algorithm==='recuris'&&!stopped) {
      const result=await call('complete');
      if(!result.accepted){a.followup(notice('Recuris working-memory checks remain incomplete. Execute substantive public checks with recuris_verify, continue work, or use recuris_stop to truthfully report incomplete work.'));return;}
    }
    const restored=await feedback();if(restored!==null){a.followup(notice('TACO restored the prior raw observation. Reconsider completion.\n'+restored));return;}
    if(state.status==='running')state.status='agent_stopped_no_official_score';
    audit('turn_stopped',{status:state.status});
  });
  audit('plugin_loaded',{algorithm:c.algorithm});
  return {state,audit,worker:()=>worker};
}
