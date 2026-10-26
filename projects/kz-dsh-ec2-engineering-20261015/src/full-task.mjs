import { actionKey, commandIdentity, digest, stable } from './policy.mjs';
import { TaskMemory, nonempty, knownDependency, normalizeMemorySupport } from './memory.mjs';
import { Subgoals } from './subgoals.mjs';
import { StructuredContext, buildContext } from './structured-context.mjs';
import { extractOutcome } from './terminal.mjs';
import { Advisory } from './advisory.mjs';
import { literalFileRead } from './commands.mjs';
import { configuration } from './policy.mjs';
import { MemoryEffects } from './memory-effects.mjs';
import { BackgroundJobs } from './background-jobs.mjs';
import { RecoveryClock } from './recovery-clock.mjs';
import { SubgoalController } from './subgoal-controller.mjs';
import { CompletionLedger } from './completion.mjs';

export function reconnaissance(command) {
  const identity = commandIdentity(command);
  if (identity[0] !== 'literal') return false;
  const executable = identity[1], args = identity[2];
  if (executable.includes('/') && !/^\/(usr\/)?bin\//u.test(executable)) return false;
  const name = executable.split('/').at(-1);
  return ['pwd','ls','cat','head','tail','wc','stat','file','grep','rg','diff'].includes(name)
    && !args.some(x => /^--(?:pre|pre-glob|output)(?:=|$)/u.test(x));
}
export function executionDefect(row) {
  if (!row.complete || row.exitCode === 0) return null;
  const text = row.stdout + '\n' + row.stderr;
  if (/\b(SyntaxError|IndentationError|TabError)\b|syntax error near/iu.test(text)) return 'syntax';
  if (/unrecognized arguments|invalid option|unknown option|missing required argument/iu.test(text)) return 'argument';
  return null;
}
export class FullTask {
  constructor(config, state = null) {
    this.config = configuration(config);
    for(const [name,value] of Object.entries({fullContextChars:config.fullContextChars??24000,memoryReserveChars:config.memoryReserveChars??8000,monitorCooldown:config.monitorCooldown??8}))
      if(!Number.isSafeInteger(value)||value<1)throw new Error(`invalid ${name}`);
    if((config.fullContextChars??24000)<8000||(config.memoryReserveChars??8000)>(config.fullContextChars??24000)/2||(config.memoryReserveChars??8000)<2000)throw new Error('memory reserve must be 2000..half of structured panel budget');
    this.state = state ?? { version: 2, taskGoal: '', evidence: {}, evidenceNext: 1, scope:'unknown',dependencies:{}, visibleEvidence:[],visibleMemories:[],urgent:[],notices:[],
      local:null, monitor:null, monitorCalls:0,lastMonitor:0,observed:0,roleSerial:0,route:null,checkpoints:[],checkpointNext:1,regressions:{},pendingRollback:null,rollbacks:0,
      critic:{ rounds:0,decision:'not_reviewed',receipts:[] }, usage:{ requests:0,tools:0,inputTokens:0,outputTokens:0,roles:{} } };
    if (this.state.version !== 2) throw new Error('unsupported full task checkpoint');
    this.state.pendingEvidence??=[];this.state.retrievedEvidence??=[];
    this.state.monitorLanes??={periodic:0,anomaly:0};this.state.startedAt??=Date.now();
    if(!this.config.backtracking){this.state.pendingRollback=null;this.state.pendingSnapshots=[];}
    this.memory = new TaskMemory(this.state.memory,config.memoryCapacity);
    this.goals = new Subgoals(this.state.subgoals);
    this.context = new StructuredContext(this.state.structured);
    this.advisory = new Advisory(this.state.advisory,config);
    this.effects = new MemoryEffects(this.state.memoryEffects);
    this.jobs = new BackgroundJobs(this.state.backgroundJobs);
    this.clock = new RecoveryClock(this.state.recoveryClock,this.state.observed);
    this.subgoalController = new SubgoalController(this.state.subgoalController);
    this.completion = new CompletionLedger(this.state.completion);
    this.state.completion=this.completion.state;
    this.state.lastMonitorClock??=this.state.lastMonitor;
    // Old timestamps counted all tools (including metadata), unlike the new
    // clock. Start a bounded fresh cooldown only if an Advisor really ran.
    if(this.state.lastAdvisorClock===undefined&&(this.state.advisorCalls??0)>0)this.state.lastAdvisorClock=this.clock.state.steps;
  }
  snapshot() { return { ...this.state,memory:this.memory.state,subgoals:this.goals.state,structured:this.context.state,advisory:this.advisory.state,memoryEffects:this.effects.state,backgroundJobs:this.jobs.state,recoveryClock:this.clock.state,subgoalController:this.subgoalController.state }; }
  recoveryRejected(call,reason,kind='gate') {
    const row=this.clock.rejected(call,reason,this.state.scope,kind);
    if(row&&this.clock.state.consecutive>=3)this.advisory.queue('rejection_stall',
      'The harness has repeatedly rejected proposals without new environment observations. Diagnose the contract or missing premise; these R records are not executed failures. Suggest one useful native observation, not another cosmetic proposal.',this.clock.state.controls.slice(-3),this.state.scope);
    return row;
  }
  notice(reason) { this.state.notices.push(String(reason)); this.state.notices=this.state.notices.slice(-8); }
  targets() { return [...new Set([...this.memory.targets(),...this.goals.targets(),...Object.keys(this.state.artifacts??{})])]; }
  trimEvidence() {
    this.completion.remember(this.state.evidence);
    // Archive hydration changes object insertion order, not event chronology.
    const ids=Object.keys(this.state.evidence).sort((a,b)=>Number(a.slice(1))-Number(b.slice(1)));
    for(const id of ids.slice(0,Math.max(0,ids.length-64)))delete this.state.evidence[id];
  }
  local(kind,error) { if (this.config.localCorrection&&!this.state.local) this.state.local={kind,error,remaining:3,instruction:'Keep the requirement; repair only the reported syntax/parameter defect.'}; }
  metadata(value) {
    const results = {};
    if (value.subgoal_plan || value.subgoal_update || value.subgoal_id) {
      try { results.subgoals=this.goals.admit(value); }
      catch (e) { this.goals.state.notices=[e.message]; results.subgoals={ignored:e.message,known_goal_ids:Object.keys(this.goals.state.items),active:this.goals.state.active,instruction:'The rejected plan was not created. Use an existing G ID, or correct subgoal_plan before referencing a new ID. This metadata error does not block useful tools.'}; }
    }
    if (value.verification_evidence) {
      try {
        if (results.subgoals?.ignored) throw new Error('Fix the rejected subgoal definition before binding evidence.');
        results.verification=this.goals.bindVerification(value.verification_evidence,this.state.evidence,this.state.dependencies);
      } catch(e) { results.verification={ignored:e.message}; }
    }
    if (value.memory) {
      try { results.memory=this.memory.admit(value.memory,this.state.evidence,Object.keys(this.state.evidence),this.state.scope,this.state.dependencies); }
      catch (e) { results.memory={ignored:e.message}; }
    }
    if (value.context_update) {
      try { this.context.update(value.context_update,this.state.evidence); results.context='accepted'; }
      catch (e) { results.context={ignored:e.message}; }
    }
    return results;
  }
  reviewProposal(proposal) {
    if(proposal.memory_review===undefined)return;
    if(!proposal.memory_review||typeof proposal.memory_review!=='object'||!Array.isArray(proposal.memory_review.ids))throw new Error('optional memory_review needs an object and an ids array');
    this.memory.review(proposal.memory_review,this.state.visibleMemories);
    if (this.state.visibleMemories.length && !nonempty(proposal.strategy_adjustment)) throw new Error('give a concrete adjustment after memory review');
  }
  before(call,policy,scope,commandDependencies={}) {
    const s=this.state, nativeEdit=['edit','write'].includes(call.name), readonly=!nativeEdit&&this.config.reconnaissanceEnabled&&reconnaissance(call.arguments.command ?? ''), correcting=!nativeEdit&&this.config.localCorrection&&s.local?.remaining>0;
    const pending=policy.state.pending;
    // Urgent applicable blockers are shown even when generic keyword recall missed them.
    const hits=this.memory.matchAction(call,scope,s.dependencies,Object.keys(commandDependencies));
    if (hits.some(m => !s.visibleMemories.includes(m.id))) {
      s.urgent=hits.map(m=>m.id);
      this.notice('Applicable memory is available; review its conditions. A recalled claim alone is not an execution ban.');
    }
    if (pending?.tool===call.name && stable(pending.arguments)===stable(call.arguments)&&pending.memory_review!==undefined) {
      try {
        this.reviewProposal(pending);
      }
      catch(e) { this.notice(`Memory review unavailable: ${e.message}; no endorsement inferred.`);delete pending.memory_review; }
    }
    const bound=pending?.tool===call.name&&stable(pending.arguments)===stable(call.arguments);
    if(nativeEdit) {
      policy.state.pending=null;
      this.effects.bind(call,bound?pending.memory_review:null,scope,hits.map(m=>m.id));
      return {allowed:true,route:'native_memory_review',reason:policy.state.advisory?'advisory_mode':'native_repair_admitted'};
    }
    // One retry needs both a bounded explicit plan and a newly observed receipt;
    // merely rewriting the explanation cannot manufacture changed conditions.
    const prior=[...policy.state.memories].reverse().find(r=>r.key===actionKey(call));
    const review=pending?.memory_review;
    const justifiedRetry=bound&&this.retrySupported(call,prior,pending,commandDependencies);
    const decision=policy.before(call,scope,{bypassExploration:readonly||correcting,dependencies:commandDependencies,reusable:literalFileRead(call.arguments.command??''),justifiedRetry});
    if (decision.allowed && correcting) s.local.remaining--;
    if(decision.allowed)this.effects.bind(call,bound?review:null,scope,hits.map(m=>m.id));
    return {...decision,route:correcting?'local_correction':readonly?'reconnaissance':'contrastive'};
  }
  retrySupported(call,prior,pending,currentDependencies={}) {
    const review=pending.memory_review;
    if(!prior||review?.decision!=='justified_retry'||!nonempty(review.new_evidence)||!nonempty(review.hypothesis)||!Array.isArray(review.support))return false;
    const relevant=new Set(Object.keys(prior.dependencies??{}));
    return review.support.some(q=>{
      if(!q||typeof q!=='object'||Array.isArray(q)||!nonempty(q.evidence_id)||!nonempty(q.target)) {
        this.notice('Retry support ignored: each item needs evidence_id, target, field and an exact quote. No command was executed by this validation.');return false;
      }
      const row=this.state.evidence[q.evidence_id];
      const current=currentDependencies[q.target];
      return Array.isArray(pending.evidence_ids)&&pending.evidence_ids.includes(q.evidence_id)&&row?.complete&&!row.nativeToolError&&row.key!==actionKey(call)&&
        Number(row.id.slice(1))>Number(prior.id.slice(1))&&relevant.has(q.target)&&row.observedTargets?.includes(q.target)&&
        knownDependency(current)&&row.dependenciesBefore?.[q.target]===current&&row.dependenciesAfter?.[q.target]===current&&
        ['stdout','stderr'].includes(q.field)&&nonempty(q.quote)&&typeof row[q.field]==='string'&&row[q.field].includes(q.quote)&&!String(prior.observation??'').includes(q.quote);
    });
  }
  observe(call, observation, before, after, depsBefore, depsAfter, policy, rawRef) {
    if (!observation.executed) return null;
    const s=this.state, out=extractOutcome(call.arguments,observation), id=`E${s.evidenceNext++}`;
    const row={...out,id,tool:call.name,callId:call.callId,turn:call.turn??null,arguments:structuredClone(call.arguments),command:call.arguments.command,key:actionKey(call),before,after,dependenciesBefore:depsBefore,dependenciesAfter:depsAfter,observedTargets:Object.keys(call.commandDependencies??{}),rawRef};
    this.clock.execution(call);
    delete row.projection; // raw/projection remains in separate audit, not duplicated state
    const prior=Object.values(s.evidence).filter(x=>x.key===row.key).sort((a,b)=>Number(a.id.slice(1))-Number(b.id.slice(1))).at(-1);
    s.evidence[id]=row;s.scope=after;s.dependencies=depsAfter;
    if(row.jobStage&&row.jobStage!=='final') {
      this.trimEvidence();
      return {row,checks:[]}; // launches/polls are not repeated executions or completed memory effects
    }
    s.observed++;
    if(row.failureObserved||row.suspect)s.pendingEvidence.push(id);
    if(row.jobStage==='final'&&!row.complete&&!s.pendingEvidence.includes(id))s.pendingEvidence.push(id);
    const defect=executionDefect(row);
    this.advisory.observe(row,reconnaissance(row.command),defect);
    let localExempt=false;
    if(defect&&this.config.localCorrection) {
      if(s.local?.remaining===0)s.local=null;
      else {this.local(defect,(row.stderr||row.stdout).slice(0,600));localExempt=true;}
    }
    else if(out.complete) s.local=null;
    if(!localExempt&&!out.noMatch) {
      policy.state.next=Number(id.slice(1));
      // Failure text is expected in a genuine failed test, not evidence loss.
      // A contradictory exit-zero failure remains uncertain; native tool errors
      // and missing exit status never become executed-command anchors.
      policy.observe(call,{...out,complete:out.complete&&!out.nativeToolError&&(!out.suspect||out.failureObserved)},before,after,call.commandDependencies??{});
    }
    const repeated=prior?.complete && out.failureObserved && prior.exitCode===row.exitCode && prior.after===after && prior.rawHashes.stdout===row.rawHashes.stdout && prior.rawHashes.stderr===row.rawHashes.stderr;
    if(repeated||row.checkStatus==='public_check_passed') {
      const ids=repeated?[prior.id,id]:[id];
      const m={kind:repeated?'blocker':'finding',conclusion:repeated?'This exact command repeated the same observed failure; cause remains unknown.':'This explicit public pytest check passed; task success remains unverified.',
        condition:`Command: ${row.command}; observed dependencies only; external state unverified.`,targets:Object.keys(depsAfter).slice(0,4),
        next_step:repeated?'Recheck changed inputs or a discriminating retry condition.':'Re-run after related changes.',evidence_ids:ids,commandKey:row.key};
      try { this.memory.admit(m,s.evidence,ids,after,depsAfter,'observer'); } catch(e) { this.notice(e.message); }
    }
    this.goals.sync(depsAfter);
    const checks=this.goals.observe(row);
    for(const check of checks) {
      if(check.passed) s.regressions[check.id]=0;
      else if(row.complete&&row.exitCode!==0) {
        const healthy=s.checkpoints.filter(c=>c.goals.includes(check.id)&&c.scope!==after&&stable(c.definitions[check.id])===stable(check.definition)).at(-1);
        if(this.config.backtracking&&healthy&&after?.startsWith('sha256:')) {
          s.regressions[check.id]=(s.regressions[check.id]??0)+1;
          if(s.regressions[check.id]>=2&&s.rollbacks<2) s.pendingRollback=healthy.id;
        }
      }
    }
    this.effects.finish(call.callId,row);
    // Derived memory must inspect both receipts before the rolling cache can
    // evict the older one; otherwise E1 + E65 loses a genuine repeat lesson.
    this.trimEvidence();
    return {row,checks};
  }
  observeNative(call,observation,before,after,depsBefore,depsAfter,rawRef) {
    this.clock.execution(call);
    const s=this.state,id=`E${s.evidenceNext++}`;
    const row={...observation,id,tool:call.name,callId:call.callId,turn:call.turn??null,command:`${call.name} ${JSON.stringify(call.arguments)}`,key:actionKey(call),before,after,
      dependenciesBefore:depsBefore,dependenciesAfter:depsAfter,observedTargets:Object.keys(call.commandDependencies??{}),rawRef,category:['read','glob','grep'].includes(call.name)?'read':'generic',clean:false,checkStatus:'unknown',failureObserved:false,taskSuccess:null};
    s.evidence[id]=row;s.observed++;s.scope=after;s.dependencies=depsAfter;this.goals.sync(depsAfter);
    if(row.nativeToolError)s.pendingEvidence.push(id);
    this.trimEvidence();
    // Reading a source file is evidence, not a successful shell check or causal memory.
    if(['read','glob','grep'].includes(call.name)&&observation.complete)this.advisory.observe(row,true,null);
    this.effects.finish(call.callId,row);return row;
  }
  monitorLane() {
    const s=this.state;
    const clock=Math.max(this.clock.state.steps,s.observed);
    if(!this.config.monitorEnabled||(!this.config.budgetDisabled&&s.monitorCalls>=12)||clock-s.lastMonitorClock<(this.config.monitorCooldown??8))return null;
    // No lifetime role quota or fictional budget percentage in unbounded runs.
    // Retain the original cooldown and event triggers; periodic review every 24 observations.
    if(this.config.budgetDisabled===true){
      if(this.clock.state.controls.filter(r=>r.clock>s.lastMonitorClock).length>=3||s.pendingEvidence.length||Object.values(s.evidence).slice(-3).some(r=>r.failureObserved||r.checkStatus==='public_check_passed'))return 'anomaly';
      return s.observed-s.lastMonitor>=24?'periodic':null;
    }
    const progress=Math.min(1,Math.max((s.usage.tools||s.observed)/(this.config.maxTools??600),(s.usage.requests??0)/(this.config.maxRequests??800),
      this.config.wallSeconds?(Date.now()-s.startedAt)/(this.config.wallSeconds*1000):0));
    const due=Array.from({length:6},(_,i)=>(i+.5)/6).filter(x=>progress>=x).length;
    if(s.monitorLanes.periodic<due)return 'periodic';
    if(s.monitorLanes.anomaly<6&&this.clock.state.controls.filter(r=>r.clock>s.lastMonitorClock).length>=3)return 'anomaly';
    const allowance=Math.min(6,1+Math.floor(progress*6));
    if(s.monitorLanes.anomaly<allowance&&(s.pendingEvidence.length||Object.values(s.evidence).slice(-3).some(r=>r.failureObserved||r.checkStatus==='public_check_passed')||s.observed-s.lastMonitor>=24))return 'anomaly';
    return null;
  }
  monitorDue() {return this.monitorLane()!==null;}
  monitorStarted() {const lane=this.monitorLane();if(!lane)return null;this.state.monitorLanes[lane]++;this.state.monitorCalls++;this.state.lastMonitor=this.state.observed;this.state.lastMonitorClock=Math.max(this.clock.state.steps,this.state.observed);return lane;}
  acceptMonitor(review, supplied, controls={}) {
    const s=this.state, ids=review.evidence_ids,controlIds=review.control_ids??[];
    if(!['progress','necessary_retry','stalled','uncertain'].includes(review.verdict)||!nonempty(review.reason)||!Array.isArray(ids)||!Array.isArray(controlIds)||ids.length+controlIds.length<(review.verdict==='stalled'?2:1)||ids.some(id=>!Object.hasOwn(supplied,id))||controlIds.some(id=>!/^R[1-9]\d*$/.test(id)||!Object.hasOwn(controls,id))||new Set([...ids,...controlIds]).size!==ids.length+controlIds.length) throw new Error('invalid monitor evidence/verdict');
    if(review.verdict==='stalled'&&!nonempty(review.next_check)) throw new Error('stalled verdict needs discriminating check');
    s.monitor={verdict:review.verdict,reason:review.reason,evidence_ids:ids,control_ids:controlIds,next_check:review.next_check,scope:s.scope};
    s.pendingEvidence=s.pendingEvidence.filter(id=>!supplied[id]);
    this.advisory.monitor({...review,evidence_ids:[...ids,...controlIds]},{...s.evidence,...controls},s.scope);
    // A malformed optional memory must not discard a valid stagnation alarm.
    if(!Array.isArray(review.memories)||review.memories.length>2) {this.notice('monitor memories rejected: at most two automatic memories');return;}
    for(const original of review.memories) {
      try {
        const candidate=normalizeMemorySupport(original,supplied);
        if(candidate.support?.some(q=>!supplied[q.evidence_id]?.[q.field]?.includes(q.quote)))throw new Error('quote not in supplied monitor view');
        this.memory.admit(candidate,s.evidence,Object.keys(supplied),s.scope,s.dependencies,'monitor');
      }
      catch(e) { this.notice(`monitor memory rejected: ${e.message}`); }
    }
  }
  panel(policy) { return buildContext(this,policy,this.config.fullContextChars??24000,this.config.memoryReserveChars??8000); }
}
