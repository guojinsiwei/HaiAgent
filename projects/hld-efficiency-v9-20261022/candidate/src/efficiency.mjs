import {digest} from './policy.mjs';

// Exact field patches: arrays are atomic and deletions explicit. No evidence or
// control state is silently filtered out of the next Solver request.
export function contextDelta(before, after) {
  const operations=[];
  const walk=(a,b,path)=>{
    if(JSON.stringify(a)===JSON.stringify(b))return;
    if(a&&b&&typeof a==='object'&&typeof b==='object'&&!Array.isArray(a)&&!Array.isArray(b)) {
      for(const key of new Set([...Object.keys(a),...Object.keys(b)])) {
        if(!Object.hasOwn(b,key))operations.push({op:'remove',path:[...path,key]});
        else if(!Object.hasOwn(a,key))operations.push({op:'set',path:[...path,key],value:b[key]});
        else walk(a[key],b[key],[...path,key]);
      }
    } else operations.push({op:'set',path,value:b});
  };
  walk(before,after,[]);
  if(!operations.length)return null;
  const delta=JSON.stringify({mode:'field_patch',operations});
  const full=JSON.stringify({mode:'replace',value:after});
  return delta.length<full.length?delta:full;
}

export function criticView(critic) {
  const {receipts=[],...rest}=critic;
  return {...rest,receipt_count:receipts.length,receipts:receipts.slice(-2).map(r=>({
    evidence_id:r.evidence_id,passed:r.passed,gap_ids:r.gap_ids,
    requirement_quotes:r.requirement_quotes,basis:r.basis,
  })),full_ref:'kz_history id=context'};
}

export function roleOutputLimit(role,payload,route,state) {
  const maximum=route.maxTokens;
  if(!Number.isSafeInteger(maximum)||maximum<1)return maximum;
  const base=role==='monitor'||role==='advisor'?2048:role==='critic'&&payload.stage==='verdict'?6144:4096;
  // Large public contracts need room for exhaustive coverage. Keep the input
  // catalog lossless and allow the verdict/plan to name every requirement.
  const contract=role==='critic'?1024+(payload.requirement_catalog?.length??0)*160:0;
  const initial=Math.min(maximum,Math.max(base,contract));
  const failures=state.efficiency?.truncations?.[role]??0;
  return Math.min(maximum,initial*2**Math.min(failures,3));
}

export function deferPeriodicPlanner(state,planner,config) {
  if(planner.state.pending?.kind!=='route_window'||planner.state.protocolFailures||state.monitor?.verdict!=='progress')return false;
  const active=planner.active();
  if(!active||active.executions-active.reviewed_at>=config.semanticRouteWindow*3)return false;
  const claim=state.progressClaims?.last;
  const rows=(claim?.support??[]).map(x=>state.evidence[x.evidence_id]);
  const recent=active.evidence_ids_observed.slice(-8);
  if(!rows.length||rows.some(r=>!r||!r.complete||r.executed!==true||r.nativeToolError||r.semanticRoute!==active.id||!recent.includes(r.id)||!state.monitor.evidence_ids?.includes(r.id)))return false;
  state.efficiency??={};
  const signature=digest([active.id,claim]);
  if(state.efficiency.deferredProgress===signature)return false;
  state.efficiency.deferredProgress=signature;
  state.efficiency.deferredRoute=active.id;
  // Defer one window per NEW attributed observation, with a three-window
  // hard backstop. Failure/stagnation triggers retain their existing priority.
  state.efficiency.plannerDeferredUntil=active.executions+config.semanticRouteWindow;
  return true;
}

export function periodicPlannerWaiting(state,planner,config) {
  const active=planner.active();
  return state.monitor?.verdict==='progress'&&planner.state.pending?.kind==='route_window'&&!planner.state.protocolFailures&&active&&
    active.executions-active.reviewed_at<config.semanticRouteWindow*3&&
    active.executions<(state.efficiency?.plannerDeferredUntil??0)&&
    state.efficiency?.deferredRoute===active.id;
}

export function efficientReviewGuard(state,world) {
  const targets=state.delivery?.requested_artifacts??[];
  // Unknown target sets cannot manufacture a new quota by editing scratch
  // files or inventing a subgoal. Global ceiling also survives real repairs.
  const material=digest(world?[world.revision,world.submitted]:targets.length?
    [...targets].sort().map(p=>[p,state.dependencies?.[p]??'unknown']):['unspecified_delivery']);
  state.efficiency??={};
  const guard=state.efficiency.reviews??={total:0,versions:{}};
  if(guard.total>=6)return {allowed:false,reason:'efficiency_task_review_ceiling',terminal:true};
  if((guard.versions[material]??0)>=3)return {allowed:false,reason:'efficiency_delivery_review_ceiling',terminal:false};
  return {allowed:true,material};
}
export function countEfficientReview(state,admission) {
  const guard=state.efficiency.reviews;
  guard.total++;guard.versions[admission.material]=(guard.versions[admission.material]??0)+1;
}
