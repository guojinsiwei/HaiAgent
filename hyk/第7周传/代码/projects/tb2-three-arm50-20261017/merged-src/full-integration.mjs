import { mkdirSync, readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { writeEvidence } from './persistence.mjs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { createUserMessage } from '@deepseek-ai/dsh-llm';
import { fingerprint, dependencyState, bashObservation } from './workspace.mjs';
import { saveCheckpoint } from './checkpoints.mjs';
import { askRole, adviserSuggestions, MONITOR, CRITIC, ADVISOR } from './roles.mjs';
import { reconnaissance } from './full-task.mjs';
import { nonempty, normalizeMemoryTargets } from './memory.mjs';
import { extractStream, clip, stageReceiptView } from './terminal.mjs';
import { digest } from './policy.mjs';
import { deliveryPaths, progressView } from './progress.mjs';
import { reserveCost, settleCost, validateCostPolicy } from './budget.mjs';
import { CriticCache } from './critic-cache.mjs';
import { verificationReceipt } from './verification-receipt.mjs';
import {preflightChecks,coverageValid} from './review-policy.mjs';
import { recordArtifactStates } from './artifacts.mjs';

export const FULL_INSTRUCTION = `KZ full algorithm sidecar is enabled. DSH owns execution and context compaction.
Four components: evidence-linked task memory; contrastive exploration; persistent structured state; category-aware terminal evidence extraction.
Establish and maintain a small concrete subgoal plan early. Use kz_update for metadata (it can share a Solver response with a native action), or attach the same fields to kz_strategy; no extra planner request is needed:
subgoal_plan:[{id:"G1",title:"parser",acceptance:"public requirement",depends_on:[],targets:["parser.py"],verification:{arguments:{command:"python -m pytest tests/test_parser.py",description:"check parser"},stdout_contains:["passed"]}}], subgoal_id:"G1".
Prefer a small focused plan, but retain all declared goals and prerequisites. Invalid verification stays pending instead of discarding the plan. Cycles/missing prerequisites require diagnostic repair, never bypass. subgoal_plan cannot silently replace an existing definition.
Use subgoal_update:{id:"G1",reason:"why this public check is appropriate",expected_revision:1,verification:{arguments:{command:"python check.py"},stdout_contains:["passed"]}} to explicitly revise it. Targets/acceptance/dependencies can also be revised; old proof is invalidated. status may only be blocked|deferred|pending, never self-declared passed.
verification_evidence:{subgoal_id:"G1",evidence_id:"E42",revision:2} binds an already-observed check to the current goal version. The exact command, clean receipt, output assertions and current file fingerprints must match. May accompany subgoal_update. check_passed is NOT official success. Invalid metadata gets feedback, not a fatal protocol error.
For a real test that is SILENT on success, explicitly declare verification:{arguments:{command:"python -m doctest module.py"},exit_code:0,stdout_contains:[]}. Do not invent a success marker or replace a test with echo. The controller chooses the ready goal and advances after actual verification; failures and target changes require rechecking. If a plan is rejected, it does not exist: use the returned known_goal_ids and repair the plan rather than repeatedly focusing a ghost ID.
memory:{kind:"finding|blocker|procedure",conclusion:"conditional lesson",condition:"when applicable",targets:["path"],operation:"optional operation",next_step:"next check",evidence_ids:["E1"]}.
context_update:{facts:[{text:"finding",evidence_ids:["E1"]}],unresolved_issues:[],incomplete_plans:[],analysis_and_conclusions:[],retire:[{field:"unresolved_issues",text:"exact prior item",status:"resolved",evidence_id:"E2",quote:"exact observed quote"}]}.
Omitting a pending item does NOT delete it. Do not claim causal certainty from command exit alone.
For an explicit evidence-linked retry, give kz_strategy.memory_review as {ids:["M1"],observed_result:"recorded result",applicability:"which conditions still hold",decision:"apply|recheck|different_route|not_applicable|justified_retry",reason:"brief decision summary",new_evidence:"changed condition or discriminating test for retries"}, followed by strategy_adjustment and exact arguments. Ordinary actions do not require a form merely because memories are visible.
For gated exploration, prefer kz_strategy execute:true to validate and execute the native action in the SAME call. Do not execute it again. With execute omitted, the declaration is one-shot and must match exact native arguments. Ordinary native repairs and useful observations need no memory form or novelty proof.
When submitting an explicit memory review, its IDs should include applicable blockers matched to this action, not just an unrelated visible memory. You may explain not_applicable or recheck; a blocker is not a permanent ban. A replacement proposal invalidates the previous plan even when rejected.
For an unchanged failed bash command, a discriminating retry additionally needs memory_review.hypothesis and support:[{evidence_id:"E2",target:"related.py",field:"stdout|stderr",quote:"exact new observation"}]. Cite a newer, complete observation actually targeting a dependency of the failed command. An unrelated E ID or prose alone does not establish relevance. Related source changes already allow ordinary revalidation; do not invent evidence. The hypothesis remains unverified, and at most one same-result retry is allowed.
Example: M1 records a parser failure; parser.py has since changed. Choose justified_retry, cite the change, and repeat the SAME original test. If unchanged, investigate a different hypothesis rather than rewording the command.
Quoted retry support must still describe the CURRENT target fingerprint; a quote from an intervening version is stale. Malformed support yields recoverable feedback, never a fatal task stop.
Native background/promoted bash is allowed. KZ links its job id to the original command, observes output without consuming your job_output cursor, and records a terminal outcome once. Collect relevant jobs with native job_output; partial output, missing jobs and kills cannot prove a successful check. Interleaved actions have unknown state attribution.
Local syntax/parameter correction and simple read-only reconnaissance do not require three-dimensional novelty; unchanged failed duplicates still have a final check. Native reads and edits remain available without mandatory memory metadata.
Any already-observed task-local E ID may be cited; the small display window is not an admission limit. Archived IDs are automatically checked. Use kz_history to inspect full text, search literal text, or read a DSH turn. A valid historical ID alone does not prove the current state or justify retry. Excerpts and missing records are not evidence of absence. Model-written memories are fallible.
Use kz_consult with {question:"one concrete difficulty"} for an independent adviser, not a second executor. Advice is optional and shares the task request budget.
Monitor-stalled, repeated identical execution failures, or extended unchanged read-only diagnosis can automatically request this SAME adviser before the next action. Alarms are hypotheses, not proof. Automatic and requested advice share cooldown and limits; no command is injected automatically.
Recovery cooldown advances on admitted native actions AND KZ-rejected proposals/actions, once per call. R IDs describe control rejections, not executed commands and never durable failure memory. Three consecutive rejections can request an adviser within the existing shared budgets/cooldown. Monitor can review these records even without new E output.
By default an exploration episode ends after eight admitted exploration probes or two orthogonality rejections, then has a four-step cooldown advanced by native actions or KZ rejections. Routine reads, native repairs and verification after changed inputs are auxiliary actions; they retain ordinary task cost/time/tool budgets. Declare one exploration hypothesis and distinguishable supports/refutes observations in the same kz_strategy call. Consult exploration.results when selecting the next probe or repair. Both/neither predictions or incomplete execution remain unknown. This disables only the temporary orthogonality gate, not task execution. The rejection exit requests a task-relevant read-only check from Solver, not an automatically injected shell command. The seven-rejection advisory fallback remains nonfatal; no rejection limit kills the task.
Before ending, an independent Critic reviews public checks. Concrete unresolved gaps return to repair or verification, not automatic delivery after two reviews. Preserve gap IDs and existing subgoals. An unavailable review is not implementation failure or success. Do not repeatedly submit the same unchanged state; execute a useful check/repair or explain a specific external blocker. User cancellation and the configured server deadline remain final.
Automatic checkpoints and rollback are FROZEN in the current default profile. Do not assume that a restore point exists. No workspace-changing recovery is injected while frozen.
All roles and tools share task budgets; memory/strategy metadata calls are counted too. No prose-length fatal limits. Do not read hidden graders or reference solutions.`;

export function installFull(ctx, { input, root, audit, stateFor, persist, entries, taskInstruction = null }) {
  const auxiliarySessions=new Map(), internalCalls=new Map();
  if(input.budgetDisabled!==undefined&&typeof input.budgetDisabled!=='boolean')throw new Error('invalid budgetDisabled');
  const unlimited=input.budgetDisabled===true;
  const requests=unlimited?Infinity:input.maxRequests??800, tools=unlimited?Infinity:input.maxTools??600;
  const costPolicy=unlimited?null:input.costPolicy, wallSeconds=unlimited?null:input.wallSeconds;
  validateCostPolicy(costPolicy);
  if(wallSeconds!==undefined&&wallSeconds!==null&&(!Number.isFinite(wallSeconds)||wallSeconds<=0))throw new Error('invalid wallSeconds');
  if(!unlimited)for(const [key,value] of Object.entries({maxRequests:requests,maxTools:tools})) if(!Number.isSafeInteger(value)||value<1) throw new Error(`invalid ${key}`);
  const record=persist;
  async function refresh(entry, extra=[]) {
    if(!entry.full)return;
    entry.full.state.scope=await fingerprint(root,input.snapshot);
    entry.full.state.dependencies=await dependencyState(root,[...new Set([...entry.full.targets(),...deliveryPaths(entry.full.state.taskGoal,root),...extra])]);
    recordArtifactStates(entry.full.state,entry.full.state.dependencies);
    entry.full.goals.sync(entry.full.state.dependencies);
    const reopened=entry.full.completion.sync(entry.full.state.scope,entry.full.state.dependencies,entry.full.state.evidence,entry.full.state.observed);
    if(reopened.length)record(entry,'gaps_need_reverification',{ids:reopened});
    entry.full.completion.reconcileGoals(entry.full.goals,entry.full.state.evidence,entry.full.state.observed);
    entry.full.advisory.sync(entry.full.state.scope);
    progressView(entry.full.state,entry.full.config,entry.full.state.dependencies,root);
  }
  function hydrateEvidence(entry, args) {
    const ids=new Set();
    const add=xs=>{if(Array.isArray(xs))for(const id of xs)if(typeof id==='string')ids.add(id);};
    add(args.evidence_ids);add(args.memory?.evidence_ids);
    if(args.verification_evidence?.evidence_id)add([args.verification_evidence.evidence_id]);
    if(Array.isArray(args.memory_review?.support))add(args.memory_review.support.map(x=>x?.evidence_id));
    for(const f of ['facts','unresolved_issues','incomplete_plans','analysis_and_conclusions'])
      if(Array.isArray(args.context_update?.[f]))for(const row of args.context_update[f])add(row?.evidence_ids);
    if(Array.isArray(args.context_update?.retire))add(args.context_update.retire.map(x=>x?.evidence_id));
    for(const id of ids) {
      if(entry.full.state.evidence[id]||!/^E[1-9]\d*$/u.test(id)||Number(id.slice(1))>=entry.full.state.evidenceNext)continue;
      try {
        const row=JSON.parse(readFileSync(path.join(entry.rawDir,id+'.json'),'utf8')).evidence;
        if(row?.id!==id)throw new Error('archive ID mismatch');
        entry.full.state.evidence[id]=row;
        record(entry,'evidence_reference_loaded',{id,source:'same_task_archive',current_state_verified:false});
      } catch(error) {entry.full.notice(`Evidence ${id} unavailable: ${error.message}`);}
    }
  }
  async function metadata(entry, original) {
    hydrateEvidence(entry,original);
    const value={...original},errors={};
    if(value.memory)try{value.memory=await normalizeMemoryTargets(value.memory,root);}
    catch(error){delete value.memory;errors.memory={ignored:error.message};}
    async function goalTargets(g) {
      if(!g||!Array.isArray(g.targets))return g;
      const targets=[],warnings=[];
      for(const target of g.targets)try{targets.push(...(await normalizeMemoryTargets({targets:[target]},root)).targets);}
      catch(error){warnings.push({target,reason:error.message});}
      if(warnings.length){errors.target_warnings??=[];errors.target_warnings.push({id:g.id,warnings});}
      return {...g,targets:[...new Set(targets)],...(warnings.length?{verification:undefined}:{} )};
    }
    if(Array.isArray(value.subgoal_plan))value.subgoal_plan=await Promise.all(value.subgoal_plan.map(goalTargets));
    if(value.subgoal_update?.targets)value.subgoal_update=await goalTargets(value.subgoal_update);
    const targets=[...(value.memory?.targets??[]),...(value.subgoal_update?.targets??[]),...(Array.isArray(value.subgoal_plan)?value.subgoal_plan.flatMap(g=>g.targets??[]):[])];
    await refresh(entry,targets);
    return {...entry.full.metadata(value),...errors};
  }
  async function native(entry,args,role,signal) {
    const callId=`kz-${role}-${++entry.full.state.roleSerial}`;
    internalCalls.set(callId,entry);
    try { return await ctx.tools.execute({name:'bash',arguments:args,callId,agent:entry.agent,signal}); }
    finally { internalCalls.delete(callId); }
  }
  async function role(entry,name,system,payload,signal) {
    return askRole(ctx,entry,name,system,payload,signal,record,auxiliarySessions);
  }
  ctx.on('llm/stream',async function*(options,next) {
    const entry=entries.get(options.sessionId)??auxiliarySessions.get(options.sessionId);
    if(!entry?.full) { yield*next(); return; }
    const s=entry.full.state;
    if(wallSeconds&&(Date.now()-s.startedAt)/1000>=wallSeconds)throw new Error('Shared task elapsed-time budget exhausted; artifacts retained');
    if(s.usage.requests>=requests) throw new Error('KZ shared task request budget exhausted; artifacts retained');
    if(!unlimited&&s.cost?.boundExceeded)throw new Error('Cost reservation bound previously exceeded; verify accounting before resuming');
    const reservation=reserveCost(s,costPolicy,options);
    const roleName=auxiliarySessions.has(options.sessionId)?options.sessionId.split(':').at(-2):options.purpose??'solver';
    s.usage.requests++;s.usage.roles[roleName]=(s.usage.roles[roleName]??0)+1;
    if(roleName==='solver') s.route=Object.fromEntries(['provider','model','reasoningEffort','temperature','maxTokens'].filter(k=>options[k]!==undefined).map(k=>[k,options[k]]));
    record(entry,'request_admitted',{role:roleName,usage:s.usage});
    let usage=null,completed=false;
    try {
      for await(const chunk of next()) {
        if(chunk.type==='usage')usage=chunk.usage;
        if(chunk.type==='finish')completed=['stop','tool-calls','length','max-tokens'].includes(chunk.reason?.kind);
        yield chunk;
      }
    } finally {
      if(usage){s.usage.inputTokens+=usage.inputTokens??0;s.usage.outputTokens+=usage.outputTokens??0;}
      try{settleCost(s,costPolicy,reservation,usage,completed);}
      finally{record(entry,'request_completed',{role:roleName,usage:s.usage,cost:s.cost??null,completed});}
    }
  });
  ctx.on('tools/pre-execute',async(exec,next)=>{
    const verdict=await next(); if(verdict.kind!=='allow'||!exec.agent)return verdict;
    const entry=stateFor(exec.agent);
    if(wallSeconds&&(Date.now()-entry.full.state.startedAt)/1000>=wallSeconds)return {kind:'deny',reason:'Shared elapsed-time budget exhausted; existing artifacts retained.'};
    if(entry.full?.state.usage.tools>=tools)return {kind:'deny',reason:'Shared task tool budget exhausted; preserve partial artifacts.'};
    return verdict;
  });
  ctx.on('tools/execute',async(exec,next)=>{
    if(exec.agent) { const entry=stateFor(exec.agent); if(entry.full) {
      // Recheck here so parallel metadata/native calls cannot overrun the cap.
      if(wallSeconds&&(Date.now()-entry.full.state.startedAt)/1000>=wallSeconds)throw new Error('shared elapsed-time budget exhausted');
      if(entry.full.state.usage.tools>=tools)throw new Error('shared task tool budget exhausted');
      entry.full.state.usage.tools++;
      const counter=exec.name.startsWith('kz_')?'metadataCalls':'nativeActions';
      entry.full.state.usage[counter]=(entry.full.state.usage[counter]??0)+1;
      record(entry,'tool_admitted',{name:exec.name,callId:exec.callId,accountingClass:counter,usage:entry.full.state.usage});
    } }
    return next();
  });
  function register(name,description,execute) {
    ctx.tools.register({name,description,parameters:{type:'object',additionalProperties:true},isConcurrencySafe:()=>false,
      output:{schema:{type:'object',additionalProperties:true},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},execute});
  }
  register('kz_update','Update task-local memory, subgoals or structured context. Metadata errors do not execute or stop commands.',async(args,exec)=>{
    const e=stateFor(exec.agent);if(!e?.full)throw new Error('full KZ task required');
    const result=await metadata(e,args);record(e,'metadata',{result});return result;
  });
  register('kz_history','Read full archived task evidence in character pages; missing display text does not mean no evidence.',async(args,exec)=>{
    const e=stateFor(exec.agent);if(!e?.full)throw new Error('full task required');
    const offset=args.offset??0;if(!Number.isSafeInteger(offset)||offset<0)throw new Error('nonnegative offset required');
    function expose(row) {
      e.full.state.evidence[row.id]=row;
      e.full.state.retrievedEvidence=[...new Set([...e.full.state.retrievedEvidence,row.id])].slice(-16);
      e.full.state.visibleEvidence=[...new Set([...e.full.state.visibleEvidence,row.id])];
    }
    if(args.query!==undefined||args.turn!==undefined) {
      if(args.query!==undefined&&(!nonempty(args.query)||args.query.length>1000))throw new Error('literal nonempty query up to 1000 characters required');
      if(args.turn!==undefined&&(!Number.isSafeInteger(args.turn)||args.turn<0))throw new Error('nonnegative DSH turn sequence required');
      const files=readdirSync(e.rawDir).filter(x=>/^E\d+\.json$/.test(x)).sort((a,b)=>Number(a.slice(1,-5))-Number(b.slice(1,-5)));
      const matches=[];let next=null;
      for(let i=offset;i<files.length;i++) {
        const data=JSON.parse(readFileSync(path.join(e.rawDir,files[i]),'utf8')),row=data.evidence;
        if(args.turn!==undefined&&row.turn!==args.turn)continue;
        const rawText=JSON.stringify(data);
        if(args.query!==undefined&&!rawText.toLowerCase().includes(args.query.toLowerCase()))continue;
        expose(row);matches.push({id:row.id,turn:row.turn,command:extractStream(row.command,'read',400),stdout:extractStream(row.stdout,row.category,600),stderr:extractStream(row.stderr,row.category,400),full_ref:`kz_history id=${row.id}`});
        if(matches.length>=8){next=i+1<files.length?i+1:null;break;}
      }
      if(matches.length)e.full.state.completionHistoryReads=(e.full.state.completionHistoryReads??0)+1;
      record(e,'history_search',{ids:matches.map(r=>r.id),turn:args.turn??null});return{matches,next_offset:next,partial:next!==null};
    }
    if(!(/^[EM][1-9]\d*$/u.test(args.id)||args.id==='context'))throw new Error('task-local E/M ID, query, turn, or context required');
    const data=args.id==='context'?{original_task:e.full.state.taskGoal,structured:e.full.context.state,subgoals:e.full.goals.state,monitor:e.full.state.monitor,critic:e.full.state.critic,advice:e.full.state.advice??null}
      :args.id.startsWith('M')?e.full.memory.state.items.find(x=>x.id===args.id):JSON.parse(readFileSync(path.join(e.rawDir,args.id+'.json'),'utf8'));
    if(!data)throw new Error('memory no longer retained in bounded active store');
    if(args.id==='context')Object.assign(data,{exploration_results:e.policy.state.experiments,delivery:e.full.state.delivery,budget:e.full.state.budgetView,cost:e.full.state.cost??null,completion:{...e.full.completion.state,observationHistory:undefined,observed_result_variants:e.full.completion.state.observationHistory?.length??0},artifacts:e.full.state.artifacts??{}});
    if(args.id.startsWith('E')){e.full.state.completionHistoryReads=(e.full.state.completionHistoryReads??0)+1;expose(data.evidence);record(e,'history_read',{id:args.id,offset});}
    const text=JSON.stringify(data), limit=8000;
    return {id:args.id,offset,text:text.slice(offset,offset+limit),next_offset:offset+limit<text.length?offset+limit:null,total_chars:text.length};
  });
  function advisoryEvents(e) {for(const {event,...detail} of e.full.advisory.drain())record(e,event,detail);}
  async function consult(e,question,signal,pending=null) {
    const s=e.full.state, trigger=pending?.trigger??'main_requested', automatic=!!pending, config=e.full.advisory.config;
    const reason=signal?.aborted?'cancelled':!s.route?'model_route_unavailable'
      :!unlimited&&(s.advisorCalls??0)>=config.maxAdvisorCalls?'capacity'
      :s.usage.requests>=requests-1?'shared_budget_reserve_solver'
      :s.lastAdvisorClock!==undefined&&e.full.clock.state.steps-s.lastAdvisorClock<config.advisorCooldownTools?'cooldown':null;
    if(reason) {
      const skip=digest([trigger,reason,pending?.signature,s.usage.tools]);
      if(s.lastAdvisorSkip!==skip){record(e,'advisor_skipped',{trigger,automatic,reason});s.lastAdvisorSkip=skip;}
      return{available:false,reason};
    }
    e.full.advisory.markAttempt(pending);
    s.advisorCalls=(s.advisorCalls??0)+1;s.lastAdvisorTool=s.usage.tools;s.lastAdvisorClock=e.full.clock.state.steps;
    record(e,'advisor_trigger',{trigger,automatic,question,evidence_ids:pending?.evidence_ids??[]});
    try {
      const panel=e.full.panel(e.policy).result;
      const evidenceIds=[...new Set([...(pending?.evidence_ids??[]),...Object.values(s.evidence).filter(r=>r.complete&&r.failureObserved).slice(-3).map(r=>r.id)])];
      const sources={...s.evidence,...e.full.clock.evidence()};
      const handover={goal:s.taskGoal,trigger,question,failed_attempts_and_trigger_evidence:evidenceIds.map(id=>sources[id]).filter(Boolean).map(r=>({id:r.id,command:clip(r.command,600),exitCode:r.exitCode,controlEvent:r.controlEvent??false,executed:r.executed,reason:r.reason?clip(r.reason,1000):undefined,stdout:extractStream(r.stdout,r.category,2000),stderr:extractStream(r.stderr,r.category,2000)}))};
      const supplied=new Set([...s.visibleEvidence,...handover.failed_attempts_and_trigger_evidence.map(r=>r.id)]);
      const answer=adviserSuggestions(await role(e,'advisor',ADVISOR,{question,task:s.taskGoal,panel,handover},signal),supplied);
      s.advice={...answer,trigger,automatic,scope:s.scope,after_observed:s.observed};record(e,'advisor_response',{trigger,automatic,answer});return answer;
    }catch(error){record(e,'advisor_unavailable',{trigger,automatic,error:error.message});return{available:false,reason:error.message};}
  }
  register('kz_consult','Ask an independent adviser for at most two evidence-linked alternatives; consumes the shared task budget.',async(args,exec)=>{
    const e=stateFor(exec.agent);if(!e?.full||!nonempty(args.question))throw new Error('a concrete task question is required');
    return consult(e,args.question,exec.signal);
  });
  async function flushSnapshots(e) {
    const s=e.full.state;
    if(!e.full.config.backtracking){s.pendingSnapshots=[];s.pendingRollback=null;return;}
    for(const pending of s.pendingSnapshots??[]) {
      if(s.scope!==pending.scope||s.checkpoints.length>=10)continue;
      try {
        mkdirSync(e.checkpointDir,{recursive:true});
        const snap=await saveCheckpoint(root,e.checkpointDir,`C${s.checkpointNext++}`);
        s.checkpoints.push({...snap,goals:pending.goals,definitions:pending.definitions});record(e,'checkpoint_created',{snapshot:snap});
      }catch(error){e.full.notice(`checkpoint unavailable: ${error.message}`);}
    }
    s.pendingSnapshots=[];
  }
  async function beforeStep(payload) {
    const e=stateFor(payload.agent);if(!e.full)return true;
    const s=e.full.state;
    if(!s.taskGoal) s.taskGoal=payload.messages.filter(m=>m.source?.kind==='user').flatMap(m=>m.content.filter(b=>b.type==='text').map(b=>b.text)).join('\n');
    if(taskInstruction&&!s.taskInstruction) {
      s.wrapperTaskGoal=s.taskGoal;s.taskGoal=taskInstruction.text;
      s.taskInstruction={path:taskInstruction.path,sha256:taskInstruction.sha256,source:'explicitly_configured_public_task_file'};
      record(e,'canonical_task_bound',{instruction:s.taskInstruction,wrapper_differs:s.wrapperTaskGoal!==s.taskGoal});
    }
    await refresh(e);
    const control=e.full.subgoalController.tick(e.full.goals,{evidence:s.evidence,dependencies:s.dependencies,observed:s.observed,requests:s.usage.requests});
    s.subgoalControl=control.view;
    if(control.notice)e.full.notice(clip(control.notice,2400));
    for(const {event,...detail} of control.events)record(e,event,detail);
    await flushSnapshots(e);
    if(s.usage.requests>=requests||s.usage.tools>=tools) { record(e,'budget_exhausted',{usage:s.usage});return false; }
    if(e.full.config.backtracking&&s.pendingRollback) {
      const target=s.checkpoints.find(c=>c.id===s.pendingRollback);s.pendingRollback=null;
      if(target&&s.rollbacks<2) {
        const preserved=path.join(e.checkpointDir,`preserved-${Date.now()}`);
        const quote=x=>"'"+x.replaceAll("'","'\\''")+"'";
        const command=[process.execPath,fileURLToPath(new URL('../scripts/restore-checkpoint.mjs',import.meta.url)),root,target.path,preserved].map(quote).join(' ');
        const result=await native(e,{command,description:'Restore verified KZ task checkpoint; preserve all current files',workdir:root},'rollback',payload.signal);
        if(!result.isError&&result.value?.exitCode===0&&await fingerprint(root)===target.scope) {
          s.rollbacks++;s.regressions={};s.local=null;e.full.goals.sync({},true);
          e.policy.state.active=false;e.policy.state.pending=null;e.policy.state.failureStreak=0;
          e.full.notice('Checkpoint restored; previous passed statuses invalidated. Recheck files.');
          record(e,'rollback_completed',{target:target.id,preserved});
        } else { e.full.notice('Rollback not completed; inspect native tool result; no success claimed.');record(e,'rollback_unavailable',{target:target.id,preserved}); }
        await refresh(e);
      }
    }
    if(e.full.monitorDue()&&s.usage.requests<requests-1) {
      const lane=e.full.monitorStarted();
      const selected=Object.values(s.evidence).sort((a,b)=>Number(a.id.slice(1))-Number(b.id.slice(1))).slice(-12);
      for(const id of s.pendingEvidence.slice(0,4)) {
        if(selected.some(r=>r.id===id))continue;
        try{const row=s.evidence[id]??JSON.parse(readFileSync(path.join(e.rawDir,id+'.json'),'utf8')).evidence;s.evidence[id]=row;selected.push(row);}
        catch(error){e.full.notice(`pending evidence ${id} unavailable: ${error.message}`);}
      }
      const supplied=Object.fromEntries(selected.map(row=>[row.id,{...row,stdout:extractStream(row.stdout,row.category,3000),stderr:extractStream(row.stderr,row.category,2000)}]));
      const controls=Object.fromEntries(e.full.clock.state.controls.slice(-8).map(row=>[row.id,{...row,command:clip(row.command,500),reason:clip(row.reason,1000)}]));
      try {
        // Keep pending evidence; bound its display, not the monitor invocation.
        for(const row of Object.values(supplied)) {
          row.command=clip(row.command,600);row.stdout=extractStream(row.stdout,row.category,1000);row.stderr=extractStream(row.stderr,row.category,700);
          delete row.dependenciesBefore;delete row.dependenciesAfter;
          delete row.arguments;delete row.receiptRaw;
          if(row.shellStageReceipt)row.shellStageReceipt=stageReceiptView(row.shellStageReceipt);
        }
        const review=await role(e,'monitor',MONITOR,{task:clip(s.taskGoal,2200),task_partial:s.taskGoal.length>2200,task_ref:s.taskInstruction??'original task in host session',evidence:supplied,control_events:controls,currentScope:s.scope,
          subgoals:e.full.goals.view().goals.map(({id,status})=>({id,status})),memories:e.full.memory.state.items.slice(-4).map(m=>({id:m.id,conclusion:clip(m.conclusion,300),condition:clip(m.condition,200)}))},payload.signal);
        if(Array.isArray(review.memories)&&review.memories.length<=2) {
          const candidates=[];
          for(const candidate of review.memories)try{candidates.push(await normalizeMemoryTargets(candidate,root));}
          catch(error){e.full.notice(`monitor memory rejected: ${error.message}`);record(e,'monitor_memory_rejected',{reason:error.message});}
          review.memories=candidates;
          await refresh(e,candidates.flatMap(c=>c.targets??[]));
        }
        e.full.acceptMonitor(review,supplied,controls);record(e,'monitor_review',{review,lane,supplied_ids:Object.keys(supplied),supplied_control_ids:Object.keys(controls),recovery_clock:e.full.clock.state.steps});
      }catch(error){ e.full.notice(`Monitor unavailable: ${error.message}`);record(e,'monitor_unavailable',{error:error.message}); }
    }
    advisoryEvents(e);
    const pending=e.full.advisory.state.pending;
    if(pending)await consult(e,pending.question,payload.signal,pending);
    record(e,'context_refreshed',{usage:s.usage});return true;
  }
  ctx.on('agent/turn-stopping',async({agent,signal})=>{
    const e=stateFor(agent);if(!e.full||!e.full.config.criticEnabled)return;
    const s=e.full.state,ledger=e.full.completion;
    if(signal.aborted||s.usage.requests>=requests||s.usage.tools>=tools)return;
    await refresh(e);
    const token=()=>ledger.token({...s,subgoals:e.full.goals.state});
    const startToken=token();
    const steer=(detail,diagnosis=false)=>agent.steer(createUserMessage({content:[{type:'text',text:JSON.stringify({
      ...detail,gaps:ledger.open(),instruction:diagnosis
        ?'The completion evidence does not yet resolve the open gaps. An identical result may still come from a fresh action; it is not proof that no action occurred. Execute a concrete public check/repair, or identify the specific blocker. Repeating a final answer does not resolve the gaps.'
        :'Address the concrete gaps with a repair or discriminating public check, then revalidate affected requirements. Preserve prior subgoals. An invalid checker is not an implementation failure.'})}],
      source:{kind:'kz-critic',form:'notice',summary:diagnosis?'Unchanged submission needs a concrete next step':'Public evidence requires follow-up'}}));
    if(ledger.state.lastReview===startToken) {
      if(ledger.state.status==='completed_publicly'||ledger.state.status==='completed_with_unverified_critic')return;
      const activity=ledger.activity(s);
      if(ledger.state.diagnosed!==startToken||ledger.state.diagnosedActivity!==activity) {
        ledger.state.diagnosed=startToken;ledger.state.diagnosedActivity=activity;steer({reason:'same_evidence_submission'},true);
        record(e,'completion_blockage_diagnosis',{token:startToken,gaps:ledger.open()});
      }else {
        // This is a repeated FINAL intent after an explicit diagnosis, not a
        // count of rejected tools. Never label it success or unsolvable.
        ledger.state.status='incomplete_repeated_submission';
        record(e,'completion_incomplete',{reason:'solver_resubmitted_same_evidence_after_diagnosis',taskUnsolvable:false});
      }
      return;
    }
    record(e,'completion_intent',{token:startToken,gaps:ledger.open()});
    const coverage=()=>ledger.deterministicCoverage(input.completionRequirements,e.full.goals)&&!ledger.open().length;
    // At most ONE format-retry in this review, only with independently supplied
    // full requirement coverage. No retry allowance stacks with paid transport.
    for(let attempt=0;attempt<2;attempt++) {
    s.critic.rounds++;
    try {
      await refresh(e);
      const plan=await role(e,'critic',CRITIC,{stage:'plan_checks',original_task:s.taskGoal,task_instruction:s.taskInstruction??null,workspace:root,previous_review_error:s.critic.lastError??null,
        existing_gaps:ledger.open(),instruction:'Keep existing Gap IDs. Repair verification defects without declaring implementation failure. Propose only necessary public checks.',
        panel:attempt?{subgoals:e.full.goals.view(),delivery:s.delivery}:e.full.panel(e.policy).result},signal);
      if(!['accept','revise'].includes(plan.decision)||!Array.isArray(plan.checks)||!Array.isArray(plan.gaps))throw new Error('invalid critic plan');
      // Persist plan-stage concerns before any execution or second model turn.
      ledger.registerReview(plan,s.taskGoal);
      record(e,'critic_plan_registered',{plan,gaps:ledger.open()});
      const preflight=preflightChecks(plan,{publicTask:s.taskGoal,evidence:s.evidence});
      if(!preflight.ok||preflight.needsInformation) {
        if(!preflight.ok&&!ledger.open().length)ledger.registerReview({gaps:['Proposed verification is not executable or attributable.'],next_step:preflight.errors.join('; ')},s.taskGoal);
        s.critic.decision=preflight.ok?preflight.kind:'repair_check';
        ledger.state.status='repair_pending';
        steer({review_status:s.critic.decision,next_step:plan.next_step,check_plan_diagnostics:preflight.errors});
        ledger.state.lastReview=token();ledger.state.diagnosed=null;
        record(e,'critic_plan_needs_followup',{preflight,completion:ledger.state,paid_verdict_calls:0,check_executions:0});
        break;
      }
      const receipts=[];
      for(const check of plan.checks) {
        if(signal.aborted)throw new Error('critic cancelled');
        e.criticCache??=new CriticCache();await refresh(e,e.criticCache.targets());
        let row=e.criticCache.get(check,e.full),reused=!!row,observed=row,result=null;
        if(!row) {
          result=await native(e,check.arguments,'critic-check',signal);observed=bashObservation(result);
          const candidate=Object.values(s.evidence).at(-1);
          row=!result.isError&&candidate?.callId===`kz-critic-check-${s.roleSerial}`?candidate:null;
          await refresh(e);if(row)e.criticCache.put(check,e.full,row);
        }
        receipts.push({...verificationReceipt(check,row,observed,result,{publicTask:s.taskGoal,evidence:s.evidence}),reused_current_receipt:reused});
        if(reused)record(e,'critic_receipt_reused',{evidence_id:row.id,command:check.arguments,scope:s.scope});
      }
      const verdict=await role(e,'critic',CRITIC,{stage:'verdict',original_task:s.taskGoal,existing_gaps:ledger.open(),plan,actual_check_observations:receipts},signal);
      if(!['accept','revise'].includes(verdict.decision)||!Array.isArray(verdict.requirements)||!Array.isArray(verdict.gaps)||!Array.isArray(verdict.checks)||verdict.checks.length)throw new Error('invalid critic verdict');
      let accepted=verdict.decision==='accept'&&verdict.requirements.length>0&&!verdict.gaps.length&&
        !(Array.isArray(verdict.new_gaps)&&verdict.new_gaps.length)&&
        !(Array.isArray(verdict.gap_updates)&&verdict.gap_updates.some(g=>['open','needs_reverification'].includes(g?.status)))&&
        receipts.every(r=>r.passed)&&plan.checks.some(c=>!reconnaissance(c.arguments.command))&&coverageValid(verdict,receipts,s.taskGoal);
      s.critic.receipts.push(...receipts);s.critic.decision=accepted?'public_review_accepted':'needs_revision';
      ledger.record(verdict,receipts,{scope:s.scope,dependencies:s.dependencies,accepted,evidence:s.evidence,observed:s.observed,publicTask:s.taskGoal});
      // A final Critic check can be the first passing goal check. There may be
      // no next solver step, so persist its checkpoint before finishing too.
      await refresh(e);await flushSnapshots(e);
      if(accepted&&ledger.open().length){accepted=false;s.critic.decision='needs_revision';}
      record(e,'critic_review',{plan,verdict,receipts,accepted,officialSuccess:null});
      if(!accepted&&!signal.aborted)steer({critic_gaps:verdict.gaps,checks:receipts});
      ledger.state.lastReview=token();ledger.state.diagnosed=null;
      record(e,'completion_review',{critic:s.critic,completion:ledger.state,officialSuccess:null});
      break;
    }catch(error){
      s.critic.decision='review_unavailable';s.critic.lastError=error.message;e.full.notice(error.message);record(e,'critic_unavailable',{error:error.message});
      if(signal.aborted) {record(e,'completion_cancelled',{reason:'host_cancelled'});break;}
      await refresh(e);
      if(attempt===0&&coverage()&&s.usage.requests<requests&&s.usage.tools<tools)continue;
      if(coverage()) {
        ledger.state.status='completed_with_unverified_critic';
        record(e,'completion_unverified_critic',{coverage_source:'operator_requirement_manifest',officialSuccess:null});
      }else {
        ledger.fallback(e.full.goals,s.evidence);
        if(s.usage.requests<requests&&s.usage.tools<tools)steer({critic_unavailable:error.message,
          diagnostic:'No success has been established. Use the registered public check if one exists; otherwise obtain the missing verification information.'});
      }
      ledger.state.lastReview=token();ledger.state.diagnosed=null;
      record(e,'completion_review',{critic:s.critic,completion:ledger.state,officialSuccess:null});break;
    }
    }
  });
  return { beforeStep, refresh, metadata, internalCalls,
    saveRaw(entry,row,raw) { const file=path.join(entry.rawDir,row.id+'.json');try {writeEvidence(file,{evidence:row,native:raw});} catch(error) {entry.persistenceError=error;throw error;} },
  };
}
