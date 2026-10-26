import {digest} from './policy.mjs';

export function exactSupport(support,evidence) {
 return Array.isArray(support)&&support.length>0&&support.every(s=>
  ['stdout','stderr'].includes(s?.field)&&typeof s.quote==='string'&&s.quote.trim()&&
  evidence[s.evidence_id]?.complete===true&&evidence[s.evidence_id]?.executed===true&&
  !evidence[s.evidence_id].nativeToolError&&evidence[s.evidence_id][s.field]?.includes(s.quote));
}

export function assessProgress(review,state,catalog,supplied) {
 const previous=state.progressClaims??{seen:[]},claim=review.progress_claim;
 if(review.verdict!=='progress')return {review,accepted:false,reason:'no_progress_claim'};
 const valid=claim&&catalog.some(q=>q.id===claim.requirement_ref)&&
  ['requirement_check','hypothesis_test'].includes(claim.kind)&&
  typeof claim.predicate==='string'&&claim.predicate.trim()&&
  typeof claim.expected_basis==='string'&&claim.expected_basis.trim()&&exactSupport(claim.support,supplied)&&
  claim.support.every(x=>review.evidence_ids?.includes(x.evidence_id));
 const signature=valid?digest([claim.requirement_ref,claim.predicate,claim.expected_basis,
  claim.support.map(x=>[supplied[x.evidence_id].key,x.field,x.quote])]):null;
 if(!valid||previous.seen.includes(signature))return {accepted:false,reason:valid?'repeated_predicate_evidence':'missing_traceable_predicate',
  review:{...review,declared_verdict:'progress',verdict:'uncertain',reason:review.reason+' [Controller: no new attributable public predicate established.]'}};
 state.progressClaims={seen:[...previous.seen,signature].slice(-128),last:claim};
 return {accepted:true,reason:'new_attributed_predicate_not_machine_proven',review};
}

export function deliverySignature(state) {
 const requested=state.delivery?.requested_artifacts??[];
 const paths=[...new Set(requested.length?requested:
  Object.values(state.subgoals?.items??{}).flatMap(g=>g.definition?.targets??[]))].sort();
 return paths.length?digest(paths.map(p=>[p,state.dependencies?.[p]??'unknown'])):null;
}

// A conservative alarm, not a task failure: two unproductive monitor windows
// and 12 real executions with unchanged declared delivery request replanning.
export function stalledDelivery(state,accounting,route) {
 const signature=deliverySignature(state),rows=Object.values(state.evidence??{}).filter(r=>
  r.complete===true&&r.executed===true&&!r.nativeToolError&&r.semanticRoute===route);
 const current=Math.max(0,...rows.map(r=>Number(r.id.slice(1))));
 let track=state.deliveryWatch;
 if(!signature||accounting.accepted||!track||track.signature!==signature||track.route!==route)
  {state.deliveryWatch={signature,route,start:current,windows:0};return [];}
 if(current<=track.last)return [];
 track.last=current;track.windows++;
 const fresh=rows.filter(r=>Number(r.id.slice(1))>track.start);
 if(track.windows<2||fresh.length<12)return [];
 track.start=current;track.windows=0;
 return fresh.slice(-6).map(r=>r.id);
}
