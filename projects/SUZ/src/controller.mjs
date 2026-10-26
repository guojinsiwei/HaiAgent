import { TaskMemory } from '../frozen-hld-v8/src/memory.mjs';
import { SemanticPlanner, normalizePlan } from '../frozen-hld-v8/src/semantic-planner.mjs';
import { configuration, digest } from '../frozen-hld-v8/src/policy.mjs';
import { VisualEvidence } from './visual-evidence.mjs';
import { PROMPTS, SOLVER_RULES, OVERLAY_RULES } from './prompts.mjs';
import { VisualWarnings } from './visual-warnings.mjs';

const txt = x => typeof x === 'string' && x.trim().length > 0;
const check = (condition, message) => { if (!condition) throw new Error(message); };
const clone = structuredClone;
export class SUZController {
  constructor({ taskId, instruction, monitorEvery = 2, routeWindow = 8, visualWarnings = true, state = null }) {
    check(txt(taskId) && txt(instruction), 'task identity and original instruction required');
    check(Number.isInteger(monitorEvery) && monitorEvery > 0 && Number.isInteger(routeWindow) && routeWindow > 0, 'invalid schedule');
    this.taskId = taskId; this.instruction = instruction; this.monitorEvery = monitorEvery;
    this.warningsEnabled=visualWarnings;
    this.state = state ?? { version: 1, taskId, instruction, step: -1, current: null, frames: [], transitions: [],
      evidence: {}, pendingAction: null, recent: [], obligations: [{id:'G0',quote:instruction,predicate:instruction}],
      contractReady:false, review:null, advice:null, lastMonitor:-1, lastPlan:-1, roleErrors:[], events:[],
      supplied:{}, feedback:[], memoryEffects:[], halted:null };
    check(this.state.version === 1 && this.state.taskId === taskId && this.state.instruction === instruction, 'cross-task checkpoint rejected');
    this.memory = new TaskMemory(this.state.memory);
    this.warnings=new VisualWarnings(this.state.visualWarnings);
    this.planner = new SemanticPlanner(configuration({semanticPlannerEnabled:true, semanticReconnaissanceSteps:1,
      semanticRouteWindow:routeWindow, semanticPlannerCooldown:2, semanticMaxRoutes:6}), this.state.planner);
    if (!state) { this.planner.state.phase = 'planning'; this.planner.queue('initial'); }
    this.visual = new VisualEvidence(taskId);
  }
  // Screenshots are restored separately from an immutable on-disk frame archive.
  restoreFrames(rows) {
    for (const f of rows) this.visual.addFrame({...f,taskId:this.taskId,bytes:Buffer.from(f.base64,'base64')});
    for (const t of this.state.transitions) this.visual.addTransition({...t,taskId:this.taskId});
    for (const m of this.memory.state.items) {
      const ids = m.evidence_ids.filter(id => this.state.transitions.some(t => t.id === id));
      if(ids.length) this.visual.attachMemory({taskId:this.taskId,memory:this.memory,memoryId:m.id,transitionIds:ids});
    }
  }
  event(type, data = {}) { this.state.events.push({type,step:this.state.step,...clone(data)}); }
  snapshot() { return clone({...this.state,memory:this.memory.state,planner:this.planner.state,visualWarnings:this.warnings.state}); }
  observe({base64, metrics = null, receipt = {status:'unknown',publicMessage:'No execution receipt supplied'}}) {
    check(!this.state.halted, 'task already halted');
    const step = ++this.state.step, id = `F${step}`;
    const bytes = Buffer.from(base64,'base64');
    const frame = this.visual.addFrame({taskId:this.taskId,id,step,phase:'observation',bytes,mime:'image/png'});
    const measured=metrics&&/^[a-f0-9]{64}$/.test(metrics.pixel_sha256)?{
      pixel_sha256:metrics.pixel_sha256,
      mean_absolute_difference:Number.isFinite(metrics.mean_absolute_difference)?metrics.mean_absolute_difference:null,
      changed_pixel_fraction:Number.isFinite(metrics.changed_pixel_fraction)?metrics.changed_pixel_fraction:null}:null;
    frame.pixel_sha256=measured?.pixel_sha256??frame.sha256;
    this.state.frames.push(frame);
    this.warnings.observe(frame);
    const pending = this.state.pendingAction;
    this.state.current = id;
    if(pending) {
      check(['success','failure','unknown'].includes(receipt.status), 'invalid receipt');
      const eid=`E${step}`;
      const transition=this.visual.addTransition({taskId:this.taskId,id:eid,before:pending.frame,after:id,
        action:pending.action,receipt});
      this.state.transitions.push(transition);
      const prior=this.state.frames.find(f=>f.id===pending.frame);
      // 'unknown:visual' deliberately prevents CLI workspace-fingerprint applicability.
      const row={id:eid,complete:true,executed:true,tool:'gui',callId:pending.callId,key:pending.key,
        before:'unknown:visual',after:'unknown:visual',stdout:transition.receipt.publicMessage,stderr:'',
        semanticRoute:pending.route,frame_ids:[pending.frame,id],action:pending.action,
        image_identity_equal:prior.sha256===frame.sha256,visual_metrics:measured,task_progress:'unassessed'};
      this.state.evidence[eid]=row;
      this.planner.observe(row);
      this.state.recent.push(eid); this.state.recent=this.state.recent.slice(-16);
      this.state.pendingAction=null;
      this.state.review=null; // Every executed action invalidates visual completion claims.
      this.event('transition',{evidence_id:eid,receipt:transition.receipt,route:pending.route});
      const tail=this.state.recent.slice(-3).map(id=>this.state.evidence[id]);
      if(tail.length===3 && tail.every(r=>r.semanticRoute===pending.route && r.image_identity_equal && r.key===tail[0].key)) {
        this.planner.queue('repeated_visual_action',tail.map(r=>r.id));
        this.event('loop_candidate',{kind:'same_action_same_pixels',evidence_ids:tail.map(r=>r.id),semantic_proof:false});
      }
      const cycle=this.state.recent.slice(-4).map(id=>this.state.evidence[id]);
      const hashes=cycle.length===4?[cycle[0].frame_ids[0],...cycle.map(r=>r.frame_ids[1])]
        .map(id=>this.state.frames.find(f=>f.id===id).pixel_sha256):[];
      if(hashes.length===5&&cycle.every(r=>r.semanticRoute===pending.route)&&hashes[0]!==hashes[1]&&
          hashes[0]===hashes[2]&&hashes[2]===hashes[4]&&hashes[1]===hashes[3]) {
        this.state.loopCandidate={kind:'page_oscillation_ABABA',evidence_ids:cycle.map(r=>r.id),step};
        this.event('loop_candidate',{...this.state.loopCandidate,semantic_proof:false});
      } else if(tail.length===3&&tail.every(r=>r.semanticRoute===pending.route&&r.visual_metrics?.mean_absolute_difference!==null&&
          r.visual_metrics?.mean_absolute_difference<0.004&&r.visual_metrics?.changed_pixel_fraction<0.02)) {
        this.state.loopCandidate={kind:'low_visual_change',evidence_ids:tail.map(r=>r.id),step};
        this.event('loop_candidate',{...this.state.loopCandidate,semantic_proof:false});
      }
      const active=this.planner.active();
      if(active && active.executions-active.reviewed_at>=this.planner.config.semanticRouteWindow)
        this.planner.queue('route_window',this.state.recent.slice(-4));
    }
    this.event('observation',{frame_id:id,sha256:frame.sha256});
    return this.schedule();
  }
  schedule() {
    const s=this.state;
    return {step:s.step,contract:!s.contractReady,monitor:s.recent.length>0 && (s.step-s.lastMonitor>=this.monitorEvery||
      s.loopCandidate?.step===s.step&&s.lastMonitor!==s.step||this.warnings.view().some(w=>w.status==='needs_revalidation')&&s.lastMonitor!==s.step),
      plan:!!this.planner.state.pending && (s.lastPlan<0 || s.step-s.lastPlan>=2),
      trigger:this.planner.state.pending?.kind??null,halted:s.halted};
  }
  context(role, stage = null) {
    check(role in PROMPTS || role==='solver','unknown role');
    check(this.state.current,'observation required');
    const route=this.planner.view();
    const query=[this.instruction,route.active_route?.hypothesis,route.active_route?.mechanism,
      ...this.state.recent.slice(-2).map(id=>this.state.evidence[id].action.description??'')].join(' ');
    const memory=this.memory.recall(query,'unknown:visual',{},4);
    const transitions=this.state.recent.slice(this.state.loopCandidate?.step===this.state.step?-4:-3);
    // Limit original image recall to two memory records, retaining textual recall of four.
    const visual=this.visual.forRole({taskId:this.taskId,role,currentFrameId:this.state.current,
      memory:this.memory,recalledMemoryIds:memory.slice(0,2).map(m=>m.id),transitionIds:transitions});
    const evidenceIds=visual.transitions.map(t=>t.id);
    const evidence=Object.fromEntries(evidenceIds.map(id=>[id,this.state.evidence[id]]));
    const payload={task_id:this.taskId,original_task:this.instruction,stage,frame_id:this.state.current,
      evidence,memory,planner:route,retained_routes:clone(this.planner.state.routes),
      next_route_id:`D${this.planner.state.nextRouteId}`,advice:this.state.advice,
      obligations:this.state.obligations,review:this.state.review,feedback:this.state.feedback.slice(-4),
      loop_candidate:this.state.loopCandidate?.step===this.state.step?this.state.loopCandidate:null,
      visual_warnings:role==='critic'||!this.warningsEnabled?[]:this.warnings.view(),
      previous_error:this.state.roleErrors.filter(e=>e.role===role).at(-1)??null,
      visual:{...visual,frames:visual.frames.map(({dataUrl,...f})=>f)}};
    this.state.supplied[role]={frame_ids:visual.frames.map(f=>f.id),evidence_ids:evidenceIds,memory_ids:memory.map(m=>m.id)};
    return {system:role==='solver'?SOLVER_RULES+'\n'+OVERLAY_RULES:PROMPTS[role],payload,images:visual.frames};
  }
  refs(role, ids, minimum=1) {
    check(Array.isArray(ids)&&ids.length>=minimum&&new Set(ids).size===ids.length&&
      ids.every(id=>this.state.supplied[role]?.evidence_ids.includes(id)), 'unknown or missing evidence IDs');
  }
  apply(role, answer, stage=null) {
    check(this.state.supplied[role], 'role must see context before answering');
    if(role==='planner') {
      const visible=this.state.supplied.planner.memory_ids;
      if(visible.length) this.memory.review(answer.memory_review,visible);
      this.planner.started(this.state.step); this.state.lastPlan=this.state.step;
      const supplied=Object.fromEntries(this.state.supplied.planner.evidence_ids.map(id=>[id,this.state.evidence[id]]));
      for(const id of this.state.supplied.planner.frame_ids) {
        const frame=this.state.frames.find(f=>f.id===id);
        supplied[id]={id,kind:'visual_observation',frame_ids:[id],sha256:frame.sha256,
          complete:false,executed:false,task_progress:'unassessed'};
      }
      const normalized=normalizePlan(answer,this.planner.state);
      this.planner.accept(normalized,supplied,this.state.step);
      if(visible.length) {
        const effect={route:this.planner.state.active,review:clone(answer.memory_review),causal_benefit_proven:false};
        this.planner.active().memory_use=answer.memory_review.ids.map(id=>({id,
          decision:answer.memory_review.decision,reason:answer.memory_review.reason}));
        this.state.memoryEffects.push(effect);this.event('memory_route_binding',effect);
      }
    } else if(role==='monitor') {
      check(['progress','stalled','uncertain','regression'].includes(answer.verdict)&&txt(answer.reason),'invalid monitor verdict');
      this.refs(role,answer.evidence_ids,answer.verdict==='stalled'?2:1);
      check(answer.evidence_ids.includes(this.state.recent.at(-1)), 'monitor needs latest transition');
      this.state.lastMonitor=this.state.step;
      if(['stalled','regression'].includes(answer.verdict)) {
        const active=this.planner.state.active;
        if(answer.evidence_ids.filter(id=>this.state.evidence[id].semanticRoute===active).length>=2)
          this.planner.queue('visual_monitor_stalled',answer.evidence_ids);
      }
      for(const candidate of answer.memories??[]) {
        try {
          this.refs(role,candidate.evidence_ids);
          const item=this.memory.admit({...candidate,targets:[],claim_type:'hypothesis'},this.state.evidence,
            this.state.supplied.monitor.evidence_ids,'unknown:visual',{},'visual_monitor');
          this.visual.attachMemory({taskId:this.taskId,memory:this.memory,memoryId:item.id,transitionIds:item.evidence_ids});
          this.event('memory_admitted',{id:item.id,evidence_ids:item.evidence_ids,status:item.status});
        } catch(error) { this.event('memory_rejected',{reason:error.message}); }
      }
      this.state.feedback.push({role,verdict:answer.verdict,reason:answer.reason,evidence_ids:answer.evidence_ids});
      if(this.warningsEnabled)for(const update of answer.warning_updates??[]) {
        try {
          const item=this.warnings.update(update,this.state.frames.at(-1));
          this.event('visual_warning_updated',{id:item.id,status:item.status,reason:update.reason});
        }catch(error){this.event('visual_warning_rejected',{reason:error.message});}
      }
    } else if(role==='advisor') {
      check(Array.isArray(answer.alternatives)&&answer.alternatives.length>0&&answer.alternatives.length<=2,'invalid alternatives');
      for(const a of answer.alternatives) {
        check(txt(a.hypothesis)&&txt(a.check)&&txt(a.difference),'incomplete advisor alternative');this.refs(role,a.evidence_ids);
      }
      this.state.advice=clone(answer);
      if(this.warningsEnabled)for(const warning of (answer.visual_warnings??[]).slice(0,3)) {
        try {
          this.refs(role,warning.evidence_ids,2);
          const draft=new VisualWarnings(clone(this.warnings.state));
          const item=draft.add(warning,this.state.frames.at(-1),this.state.evidence,null);
          const memory=this.memory.admit({kind:'blocker',conclusion:`${warning.target}: ${warning.diagnosis}`,
            condition:warning.condition,operation:warning.target,evidence_ids:warning.evidence_ids,targets:[],claim_type:'hypothesis'},
            this.state.evidence,this.state.supplied.advisor.evidence_ids,'unknown:visual',{},'visual_advisor');
          item.memory_id=memory.id;this.warnings=draft;
          this.visual.attachMemory({taskId:this.taskId,memory:this.memory,memoryId:memory.id,transitionIds:memory.evidence_ids});
          this.event('visual_warning_admitted',{id:item.id,memory_id:memory.id,style:item.style,evidence_ids:item.evidence_ids});
        } catch(error){this.event('visual_warning_rejected',{reason:error.message});}
      }
    } else if(role==='critic') {
      if(stage==='plan') {
        check(Array.isArray(answer.obligations)&&answer.obligations.length>0,'critic obligations required');
        const ids=new Set();
        for(const o of answer.obligations) {
          check(/^G\d+$/.test(o.id)&&!ids.has(o.id)&&txt(o.quote)&&this.instruction.includes(o.quote)&&txt(o.predicate),'invalid public obligation');ids.add(o.id);
        }
        check(!this.state.contractReady,'obligations immutable');
        // IDs carry no evidence at planning time. Preserve every predicate and quote,
        // assigning fresh IDs if a model echoes reserved G0; never replace the original goal.
        const obligations=clone(answer.obligations);
        if(ids.has('G0')) {
          obligations.forEach((o,index)=>{o.id=`G${index+1}`;});
          this.event('obligation_ids_normalized',{reason:'reserved G0 echoed',count:obligations.length});
        }
        this.state.obligations.push(...obligations);this.state.contractReady=true;
      } else {
        check(this.state.contractReady,'critic contract missing');
        check(['accept','revise','insufficient'].includes(answer.decision)&&Array.isArray(answer.assessments),'invalid critic decision');
        const ids=new Set(), known=this.state.obligations.map(o=>o.id);
        for(const a of answer.assessments) {
          check(known.includes(a.id)&&!ids.has(a.id)&&['met','unmet','unknown'].includes(a.status)&&txt(a.reason),'invalid obligation assessment');ids.add(a.id);
          check(Array.isArray(a.frame_ids)&&a.frame_ids.every(id=>this.state.supplied.critic.frame_ids.includes(id)),'unknown critic frame');
          if(a.status==='met') check(a.basis==='visible_result'&&a.frame_ids.includes(this.state.current),'closure needs current visual evidence');
          else check(txt(a.next_step),'unresolved requirement needs next inspection');
        }
        check(ids.size===known.length,'critic must assess every obligation');
        const accepted=answer.decision==='accept'&&answer.assessments.every(a=>a.status==='met');
        this.state.review={...clone(answer),accepted,frame:this.state.current,official_success:null};
        this.event('completion_review',this.state.review);
      }
    } else throw new Error('unknown role');
    this.event('role_applied',{role,stage});
    for(const e of this.planner.drain())this.event(e.event,e);
    return this.schedule();
  }
  roleError(role, reason) {
    this.state.roleErrors.push({role,reason:String(reason).slice(0,400),step:this.state.step});
    if(role==='planner') {this.state.lastPlan=this.state.step;this.planner.unavailable(String(reason),this.state.step);}
    if(role==='monitor')this.state.lastMonitor=this.state.step;
    this.event('role_unavailable',{role,reason:String(reason).slice(0,400)});
  }
  propose({actions,description,points=[]}) {
    check(!this.state.halted&&!this.state.pendingAction,'pending action must be observed before next dispatch');
    check(Array.isArray(actions)&&actions.length>0&&actions.every(txt),'actions required');
    if(actions.includes('DONE')) {
      const allowed=actions.length===1&&this.state.review?.accepted===true&&this.state.review.frame===this.state.current;
      this.event('completion_requested',{allowed,official_success:null});
      return {allowed,review_required:!allowed};
    }
    if(actions.includes('FAIL')) return {allowed:actions.length===1,terminal:'failed'};
    check(Array.isArray(points)&&points.length<=8&&points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)&&
      p.x>=0&&p.x<=1&&p.y>=0&&p.y<=1),'invalid GUI click points');
    const action={name:'gui',arguments:{command:actions.join('\n'),description},description,points:clone(points)};
    const callId=`A${this.state.step}`, key=digest(actions);
    this.planner.dispatch({name:'gui',arguments:action.arguments,callId});
    this.state.pendingAction={action,callId,key,frame:this.state.current,route:this.planner.state.active};
    this.event('action_dispatched',{callId,key,route:this.planner.state.active,
      memory_use:this.planner.active()?.memory_use??[],causal_benefit_proven:false});
    for(const e of this.planner.drain())this.event(e.event,e);
    return {allowed:true};
  }
  halt(reason) { this.state.halted=reason;this.event('halt',{reason,official_success:null}); }
}
