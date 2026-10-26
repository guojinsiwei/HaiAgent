import {digest} from './policy.mjs';

// Resource guard only: evidence novelty never establishes task correctness.
// Count actual review admissions, not repeated delivery intents. A real new
// read-only observation or closed gap can justify another review without a
// mutation of application state. Hard ceiling bounds endlessly varied checks.
export function reviewAdmission(state, world, ledger) {
  const material=completionProgress(state,ledger);
  const observations=Object.values(state.evidence??{}).filter(r=>r.executed===true&&r.complete===true&&!r.nativeToolError)
    .map(r=>digest([r.key,r.exitCode,r.rawHashes??[r.stdout,r.stderr]]));
  const previous=state.materialReview;
  const fresh=observations.filter(x=>!previous?.observations.includes(x));
  if(previous?.material===material&&!fresh.length)return {allowed:false,reason:'unchanged_delivery_and_observations',reviews:state.reviewBudget?.admitted??0};
  const admission=legacyAdmission(state,world,ledger);
  if(admission.allowed)state.materialReview={material,observations};
  return admission;
}

function legacyAdmission(state, world, ledger) {
  const application=JSON.stringify(world?[world.revision,world.submitted]:[state.scope,state.dependencies]);
  // Lifetime bound survives scratch-file revisions and a changing review token.
  state.reviewBudget??={admitted:0};
  if(state.reviewBudget.admitted>=12)return {allowed:false,reason:'task_review_ceiling',reviews:state.reviewBudget.admitted};
  let guard=state.appworldReview;
  if(!guard || guard.version!==2 || guard.application!==application)
    guard=state.appworldReview={version:2,application,seen:[],reviews:0,stagnant:0};
  const observations=Object.values(state.evidence??{}).filter(r=>r.executed===true&&r.complete===true&&!r.nativeToolError)
    .map(r=>digest([r.key,r.exitCode,r.rawHashes??[r.stdout,r.stderr],r.before,r.after]));
  const facts=[...observations,...ledger.state.gaps.filter(g=>g.status==='closed').map(g=>'closed:'+g.id),
    ...Object.entries(state.subgoals?.items??{}).filter(([,g])=>g.status==='check_passed').map(([id,g])=>'goal:'+id+':'+g.revision)];
  const fresh=facts.filter(x=>!guard.seen.includes(x));
  if(guard.reviews>=8)return {allowed:false,reason:'eight_review_ceiling_for_application_revision',reviews:guard.reviews};
  if(!fresh.length&&guard.stagnant>=2)return {allowed:false,reason:'three_reviews_without_new_observations_or_closed_gaps',reviews:guard.reviews};
  guard.stagnant=fresh.length?0:guard.stagnant+1;
  guard.seen=[...new Set([...guard.seen,...facts])];guard.reviews++;
  state.reviewBudget.admitted++;
  return {allowed:true,reviews:guard.reviews,new_evidence_or_closures:fresh.length,stagnant:guard.stagnant};
}

// Controller-level repetition is independent of terminal command spelling.
// Only changed declared target contents or discharged obligations reset it.
export function completionProgress(state, ledger) {
  const goals=state.subgoals?.items??{};
  const requested=state.delivery?.requested_artifacts??[];
  const targets=[...new Set(requested.length?requested:Object.values(goals).flatMap(g=>g.definition?.targets??[]))].sort();
  return digest([targets.map(p=>[p,state.dependencies?.[p]??'unknown']),
    ledger.state.gaps.filter(g=>g.status==='closed').map(g=>g.id).sort(),
    Object.entries(goals).filter(([,g])=>g.status==='check_passed').map(([id,g])=>[id,g.revision])]);
}

export function reviewRecovery(state, ledger) {
  const progress=completionProgress(state,ledger);
  let r=state.reviewRecovery;
  if(!r||r.progress!==progress)r=state.reviewRecovery={progress,followups:0,replanned:false};
  return r;
}

export function bindPlanGaps(plan,ledger) {
  for(const check of plan.checks??[]) {
    const refs=check.gap_refs??[];
    const ids=refs.flatMap(ref=>ledger.open().filter(g=>g.detail===ref).map(g=>g.id));
    check.gap_ids=[...new Set([...(check.gap_ids??[]),...ids])];
  }
}
