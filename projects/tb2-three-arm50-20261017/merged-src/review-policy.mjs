import {maskedStages} from './commands.mjs';

const text=x=>typeof x==='string'&&x.trim().length>0;
const strings=x=>Array.isArray(x)&&x.every(text);

// This validates attribution and traceability, not domain truth or authorship.
export function checkBasis(check,{publicTask='',evidence={}}={}) {
  const p=check.provenance??{},sources=Array.isArray(p.sources)?p.sources:[];
  const grounded=sources.length>0&&sources.every(s=>text(s.quote)&&(s.kind==='task'
    ?publicTask.includes(s.quote)
    :s.kind==='evidence'&&['stdout','stderr'].includes(s.field)&&evidence[s.evidence_id]?.complete===true&&
      !evidence[s.evidence_id]?.nativeToolError&&typeof evidence[s.evidence_id]?.[s.field]==='string'&&evidence[s.evidence_id][s.field].includes(s.quote)));
  const sourceKind=['public_spec','provided_test','independent_derivation'].includes(p.kind);
  const explained=text(p.author)&&text(p.expected_rule)&&text(p.independence);
  const ruleTrace=p.kind==='independent_derivation'?text(p.derivation):sources.some(s=>s.quote?.includes(p.expected_rule));
  return {kind:p.kind??'unknown',author:p.author??'unknown',expected_rule:p.expected_rule??null,
    sources,independence:p.independence??null,derivation:p.derivation??null,
    traceable:!!(grounded&&explained&&ruleTrace),
    level:sourceKind&&grounded&&explained&&ruleTrace?'attributed_correctness_basis':'consistency_only',
    caveat:'Source references are checked; model-attributed independence and domain correctness are not machine-proven.'};
}

export function preflightChecks(plan,context) {
  if(!Array.isArray(plan.checks)||plan.checks.length>2)return {ok:false,kind:'repair_check',errors:['checks must be an array of at most two public checks']};
  if(!plan.checks.length) {
    const valid=plan.decision==='revise'&&['missing_information','missing_capability','repair_check','repair_implementation'].includes(plan.reason_kind)&&text(plan.next_step)&&Array.isArray(plan.gaps)&&plan.gaps.length>0;
    return {ok:valid,kind:valid?plan.reason_kind:'repair_check',needsInformation:valid,
      errors:valid?[]:['A no-check revision needs reason_kind, a concrete gap and next_step.']};
  }
  const errors=[];
  for(const [i,c] of plan.checks.entries()) {
    const command=c?.arguments?.command;
    if(!text(command)||/^(true|echo|printf|:)\b/u.test(command.trim())||maskedStages(command??'')||/\b(?:bash|sh)\s+-[a-z]*c\b/u.test(command??''))
      errors.push(`check ${i}: use a direct command with attributable exit status; prepare a script with assertions separately, not heredoc/pipeline/masked stages`);
    if(!strings(c?.stdout_contains))errors.push(`check ${i}: stdout_contains must contain exact strings, or [] for silent assertions`);
    if(!strings(c?.gap_ids??[])||!strings(c?.requirement_quotes)||!c.requirement_quotes?.length||c.requirement_quotes.some(q=>!context.publicTask.includes(q)))
      errors.push(`check ${i}: identify exact public requirement quotes and the existing gap_ids this check tests`);
    if(!text(c?.provenance?.author)||!text(c?.provenance?.kind)||!text(c?.provenance?.expected_rule))
      errors.push(`check ${i}: record checker author, expectation kind and expected_rule before execution`);
  }
  return {ok:!errors.length,kind:'repair_check',errors};
}

export function coverageValid(verdict,receipts,publicTask) {
  const mappings=verdict.requirement_evidence;
  return Array.isArray(verdict.requirements)&&verdict.requirements.length>0&&Array.isArray(mappings)&&
    verdict.requirements.every(requirement=>text(requirement)&&publicTask.includes(requirement)&&mappings.some(m=>
      m.requirement_quote===requirement&&text(m.reason)&&Array.isArray(m.evidence_ids)&&m.evidence_ids.length>0&&
      m.evidence_ids.every(id=>receipts.some(r=>r.evidence_id===id&&r.passed&&r.requirement_quotes?.includes(requirement)&&r.basis?.level==='attributed_correctness_basis'))));
}

export function closureValid(gap,update,receipts,evidence) {
  if(!text(update.reason)||!Array.isArray(update.evidence_ids)||!update.evidence_ids.length)return false;
  return update.evidence_ids.every(id=>{
    const r=receipts.find(r=>r.evidence_id===id);
    if(!r?.passed||!evidence[id]||!r.gap_ids?.includes(gap.id))return false;
    if(gap.requirement_quote&&!r.requirement_quotes?.includes(gap.requirement_quote))return false;
    // Repeating a self-authored checker cannot resolve an unverified premise.
    if(gap.proof_obligation==='correctness_basis'&&(r.basis?.level!=='attributed_correctness_basis'||r.reused_current_receipt||(gap.evidence_ids??[]).includes(id)))return false;
    return true;
  });
}
