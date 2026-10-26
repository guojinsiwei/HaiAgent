import { digest, knownState } from './policy.mjs';
import { knownDependency } from './memory.mjs';
import {verificationKey} from './verification-identity.mjs';
import {closureValid} from './review-policy.mjs';

// A task-local ledger, not a second executor. IDs belong to the harness, never
// to a model's changing prose. Unknown state invalidates proof conservatively.
export class CompletionLedger {
  constructor(state) {
    this.state=state??{version:1,next:1,gaps:[],lastReview:null,diagnosed:null,status:'working'};
    if(this.state.version!==1)throw new Error('unsupported completion ledger');
  }
  sync(scope,dependencies,evidence={},observed=null) {
    const reopened=[];
    for(const gap of this.state.gaps)if(gap.status==='closed') {
      const proof=gap.proof,targets=Object.keys(proof?.dependencies??{});
      const superseded=proof?.checks?.some(check=>Object.values(evidence).some(row=>(row.key===check.key||check.verificationKey&&row.arguments&&verificationKey(row.arguments)===check.verificationKey)&&row.executed===true&&Number(row.id?.slice(1))>Number(check.id.slice(1))));
      // An unknown hash cannot establish equality across actions. But a second
      // refresh in the SAME observation is not a new action invalidating the
      // check that has just run. Known changes invalidate even in that case.
      const sameObservation=observed!==null&&observed===proof?.observed;
      const unchanged=(old,now)=>knownDependency(old)&&knownDependency(now)?old===now:sameObservation&&old===now;
      const current=!superseded&&proof&&(targets.length?targets.every(p=>unchanged(proof.dependencies[p],dependencies[p])):
        knownState(scope)&&knownState(proof.scope)?scope===proof.scope:sameObservation&&scope===proof.scope);
      if(!current){gap.status='needs_reverification';gap.reason='related_state_changed_or_unknown';reopened.push(gap.id);}
    }
    if(reopened.length)this.state.status='repair_pending';
    return reopened;
  }
  open() {return this.state.gaps.filter(g=>g.status!=='closed');}
  reconcileGoals(goals,evidence,observed) {
    for(const gap of this.open())if(gap.key.startsWith('goal:')) {
      const goal=goals.state.items[gap.requirement_id],row=evidence[goal?.proof?.evidence];
      if(goal?.status!=='check_passed'||!goal.proof||!row)continue;
      gap.status='closed';gap.proof={scope:goal.proof.scope,observed,dependencies:{...goal.proof.dependencies},
        evidence_ids:[row.id],checks:[{key:row.key,id:row.id,verificationKey:row.arguments?verificationKey(row.arguments):null}]};
    }
  }
  upsert(key,detail) {
    let gap=this.state.gaps.find(g=>g.key===key);
    if(!gap){gap={id:`Gap-${this.state.next++}`,key,status:'open'};this.state.gaps.push(gap);}
    const prior=gap.proof_obligation;
    Object.assign(gap,detail,{status:'open'});
    if(prior==='correctness_basis')gap.proof_obligation=prior;
    delete gap.proof;return gap;
  }
  registerReview(review,publicTask='',evidenceIds=[]) {
    for(const draft of Array.isArray(review.new_gaps)?review.new_gaps:[]) {
      if(typeof draft?.requirement_quote!=='string'||!draft.requirement_quote.trim()||!publicTask.includes(draft.requirement_quote)||typeof draft.detail!=='string'||!draft.detail.trim())continue;
      this.upsert(`requirement:${digest([draft.requirement_quote,draft.detail.trim()])}`,{kind:'public_requirement_gap',
        requirement_quote:draft.requirement_quote,detail:draft.detail,
        proof_obligation:draft.proof_obligation==='behavior'?'behavior':'correctness_basis',
        evidence_ids:evidenceIds,next_step:draft.next_step});
    }
    for(const detail of Array.isArray(review.gaps)?review.gaps:[]) {
      if(typeof detail!=='string'||!detail.trim())continue;
      // Legacy strings have no stable supplied ID. Preserve each distinct
      // obligation rather than guessing that two deficiencies mean the same.
      this.upsert('review:'+digest(detail.trim()),{kind:'public_requirement_gap',detail,
        proof_obligation:'correctness_basis',requirements:review.requirements,evidence_ids:evidenceIds,
        next_step:review.next_step??'Obtain evidence that addresses the original unresolved requirement and its expected-value basis.'});
    }
  }
  record(verdict,receipts,{scope,dependencies,accepted,evidence={},observed=null,publicTask=''}) {
    const proofFor=ids=>{
      const rows=ids.map(id=>evidence[id]).filter(Boolean);
      // Equivalent duplicate checks in this SAME review do not invalidate one
      // another. A newer contradictory result must still supersede old proof.
      const current=rows.filter(row=>!rows.some(newer=>newer.key===row.key&&Number(newer.id.slice(1))>Number(row.id.slice(1))&&
        newer.exitCode===row.exitCode&&newer.complete===row.complete&&newer.stdout===row.stdout&&newer.stderr===row.stderr));
      return {scope,observed,dependencies:{...dependencies},evidence_ids:ids,checks:current.map(row=>({key:row.key,id:row.id,verificationKey:row.arguments?verificationKey(row.arguments):null}))};
    };
    this.registerReview(verdict,publicTask,receipts.map(r=>r.evidence_id).filter(Boolean));
    // Only explicit IDs and targeted receipts can close existing obligations.
    const updates=Array.isArray(verdict.gap_updates)?verdict.gap_updates:[];
    for(const update of updates) {
      if(!update||typeof update!=='object')continue;
      const gap=this.state.gaps.find(g=>g.id===update.gap_id);
      if(!gap)continue;
      if(typeof update.detail==='string')gap.detail=update.detail;
      const ids=update.evidence_ids;
      if(update.status==='closed'&&closureValid(gap,update,receipts,evidence)) {
        const bases=receipts.filter(r=>ids.includes(r.evidence_id)).map(r=>r.basis);
        const sources=bases.flatMap(b=>(b?.sources??[]).filter(s=>s.kind==='evidence').map(s=>s.evidence_id));
        gap.status='closed';gap.proof={...proofFor([...new Set([...ids,...sources])]),reason:update.reason,bases};
      }else if(update.status==='closed') {gap.closure_rejected='Missing targeted receipt, traceable basis or specific closure reason';
      }else if(['open','needs_reverification'].includes(update.status)) {gap.status=update.status;delete gap.proof;}
      // Unknown/fabricated IDs and prose-only closure never become proof.
    }
    if(!accepted)for(const receipt of receipts.filter(r=>!r.passed))this.upsert(`check:${digest(receipt.command)}`,{
      kind:receipt.command_execution==='failed'?'check_failed':'verification_missing',detail:receipt.harness_diagnostic,
      evidence_ids:receipt.evidence_id?[receipt.evidence_id]:[],next_step:receipt.command});
    this.state.status=accepted&&!this.open().length?'completed_publicly':'repair_pending';
  }
  fallback(goals,evidence) {
    for(const [id,goal] of Object.entries(goals.state.items))if(goal.status!=='check_passed') {
      const row=evidence[goal.lastEvidence];
      this.upsert(`goal:${id}`,{kind:row?.failureObserved?'check_failed':'verification_missing',
        requirement_id:id,detail:`${id} has no current verified acceptance receipt. This does not prove its implementation is wrong.`,
        evidence_ids:row?[row.id]:[],next_step:goal.definition.verification?.arguments??'Discover an appropriate public check; do not invent a passing marker.'});
    }
    this.state.status='review_unavailable';
  }
  // Only an operator-supplied complete requirement manifest can enable this
  // fallback. A model-created set of subgoals is NOT coverage of the whole task.
  deterministicCoverage(requirements,goals) {
    return Array.isArray(requirements)&&requirements.length>0&&requirements.every(r=>
      typeof r.id==='string'&&Array.isArray(r.goalIds)&&r.goalIds.length>0&&r.goalIds.every(id=>goals.state.items[id]?.status==='check_passed'));
  }
  activity(state) {
    // Only real execution observations and successful archive reads establish
    // activity. Metadata chatter and a reworded final answer cannot do so.
    return digest([Object.values(state.evidence??{}).filter(r=>r.executed===true).map(r=>[
      r.id,r.callId??null,r.jobStage??null,r.rawHashes??digest([r.stdout,r.stderr]),r.complete
    ]),state.completionHistoryReads??0]);
  }
  remember(evidence) {
    // State keeps a bounded recent window. Retain only semantic hashes before
    // rows move to the task archive, so compaction/eviction cannot erase B.
    this.state.observationHistory=[...new Set([...(this.state.observationHistory??[]),
      ...Object.values(evidence??{}).map(row=>digest([
        row.key,row.exitCode,row.complete,row.rawHashes??digest([row.stdout,row.stderr]),row.nativeToolError??false
      ]))])].sort();
    return this.state.observationHistory;
  }
  token(state) {
    const latest=Object.values(state.evidence??{}).sort((a,b)=>Number(b.id?.slice(1))-Number(a.id?.slice(1)))[0];
    const observation=latest?[latest.key,latest.exitCode,latest.complete,latest.rawHashes??digest([latest.stdout,latest.stderr]),latest.nativeToolError??false]:null;
    // Keep every distinct observed result in the review identity. The latest
    // receipt alone loses an intervening B when a later check returns to A.
    // Renumbered copies of identical evidence must not buy another review.
    const history=this.remember(state.evidence);
    return digest([state.scope,state.dependencies,observation,history,this.state.gaps.map(g=>[g.id,g.status]),
      Object.entries(state.subgoals?.items??{}).map(([id,g])=>[id,g.revision,g.status])]);
  }
}
