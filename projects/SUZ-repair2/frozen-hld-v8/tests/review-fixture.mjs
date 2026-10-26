// Upgrade legacy mock replies to the explicit EC3 protocol. Only test adapters
// call this helper; production never manufactures coverage or closure mappings.
export function fixtureReview(payload,value) {
  if(!payload.stage||!value?.decision)return value;
  const requirement=payload.original_task;
  if(payload.stage==='plan_checks'&&value.checks?.length) return {...value,checks:value.checks.map(c=>({...c,
    gap_ids:payload.existing_gaps.map(g=>g.id),requirement_quotes:[requirement],
    provenance:{author:'test-fixture',kind:'public_spec',expected_rule:requirement,
      sources:[{kind:'task',quote:requirement}],independence:'Fixture expected behavior is supplied by the test, not inferred from candidate code.'}}))};
  if(payload.stage==='plan_checks'&&value.decision==='revise'&&!value.checks?.length)
    return {...value,reason_kind:'missing_information',next_step:'Observe the fixture public check before requesting review.'};
  if(payload.stage==='verdict'&&value.decision==='accept') {
    const receipts=payload.actual_check_observations;
    return {...value,requirements:[requirement],requirement_evidence:[{requirement_quote:requirement,evidence_ids:receipts.map(r=>r.evidence_id).filter(Boolean),reason:'Fixture checks the supplied behavior.'}],
      gap_updates:payload.existing_gaps.map(g=>({gap_id:g.id,status:'closed',evidence_ids:receipts.filter(r=>r.gap_ids.includes(g.id)).map(r=>r.evidence_id).filter(Boolean),reason:'The explicitly targeted fixture receipt resolves this gap.'}))};
  }
  return value;
}
