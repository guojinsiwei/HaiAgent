// Task-local, evidence-bound exploration memory. No model calls or semantic oracle.
export const DIMENSIONS=['dependency_dimension','target_dimension','command_dimension'];
const terms=x=>new Set(String(x??'').toLowerCase().match(/[\p{L}\p{N}_.-]+/gu)??[]);
const overlap=(a,b)=>[...a].filter(x=>b.has(x)).length;
const text=x=>typeof x==='string'&&x.trim().length>0&&!x.includes('\0');

export function validateComparison(proof,changed) {
  if(!proof||DIMENSIONS.some(k=>!text(proof[k])))throw new Error('Active exploration requires all three comparison fields; state what stays unchanged.');
  if(!Array.isArray(changed)||!changed.length||changed.some(x=>!DIMENSIONS.includes(x)))throw new Error('Active exploration requires changed_dimensions naming at least one relevant dimension.');
}
export function validateExperiment(value) {
  if(!value||typeof value!=='object'||!text(value.hypothesis))throw new Error('Active exploration requires an exploration hypothesis and supports/refutes observations.');
  for(const k of ['supports','refutes']) {
    const p=value[k];
    if(!p||!['stdout','stderr'].includes(p.field)||!text(p.contains)||p.contains.length>240)throw new Error('Exploration predictions need field stdout|stderr and a nonempty contains literal (max 240).');
  }
  const a=value.supports,b=value.refutes;
  if(a.field===b.field&&(a.contains.includes(b.contains)||b.contains.includes(a.contains)))throw new Error('Exploration predictions must distinguish support from refutation.');
  return {hypothesis:value.hypothesis,supports:{field:a.field,contains:a.contains},refutes:{field:b.field,contains:b.contains}};
}

export function selectAnchors(rows,{triggerKey=null,query='',targets=[],goal=null,limit=3}={}) {
  const groups=new Map(),q=terms(query),wanted=new Set(targets);
  for(const row of rows) {
    const key=row.check_key??row.key,prev=groups.get(key);
    const evidence=[...(prev?.evidence_ids??[]),row.evidence_id??row.id].slice(-4);
    groups.set(key,{...row,attempts:(prev?.attempts??0)+1,evidence_ids:evidence,
      conditions_changed:!!prev&&(prev.scope!==row.scope||prev.conditions_changed===true)});
  }
  return [...groups.values()].map((row,index)=>({row,index,score:
    (row.check_key===triggerKey&&triggerKey?1000:0)+(goal&&row.goal===goal?30:0)+
    8*Object.keys(row.dependencies??{}).filter(x=>wanted.has(x)).length+
    overlap(q,terms(`${row.command} ${row.observation}`))}))
    .filter(x=>x.score>0||(!query&&!targets.length&&!goal&&!triggerKey))
    .sort((a,b)=>b.score-a.score||b.index-a.index).slice(0,limit).map(x=>x.row);
}

export function resultMemory(plan,out,{id,command,before,after,dependencies={}}) {
  const usable=out.executed!==false&&out.complete===true&&Number.isInteger(out.exitCode)&&
    !out.timedOut&&!out.aborted&&!out.blocked&&!out.sandbox?.denied&&!out.nativeToolError&&!out.localDefect&&!(out.exitCode===0&&out.clean===false);
  const matches=k=>usable&&String(out[plan.experiment[k].field]??'').includes(plan.experiment[k].contains);
  const support=matches('supports'),refute=matches('refutes');
  const status=support!==refute?(support?'supported':'refuted'):'unknown';
  const evidence=[];
  for(const k of ['supports','refutes'])if(matches(k))evidence.push({field:plan.experiment[k].field,quote:plan.experiment[k].contains});
  return {id:`X${id}`,evidence_id:id,episode:plan.episode,anchor_ids:plan.anchor_ids,
    check_key:plan.check_key,goal:plan.goal??null,kind:plan.kind,command,
    hypothesis:plan.experiment.hypothesis,predictions:{supports:plan.experiment.supports,refutes:plan.experiment.refutes},
    status,reason:!usable?'execution_unusable':support&&refute?'conflicting_observations':!support&&!refute?'no_predicted_observation':'exclusive_predicted_observation',
    evidence,conditions:{before,after,dependencies:{...dependencies}},
    semantic_verified:false,task_success:null,
    next_use:status==='refuted'?'Reconsider this hypothesis under the recorded conditions; cite new evidence before retrying it.':
      status==='supported'?'Use this observation to choose a repair or verification; the causal explanation remains a hypothesis.':
      'This attempt did not distinguish the hypothesis; inspect the failure or choose a different observation.'};
}

export function recallResults(rows,{query='',checkKey=null,goal=null,scope=null,dependencies={},limit=3}={}) {
  const q=terms(query);
  return rows.map((row,index)=>({row,index,score:(checkKey&&row.check_key===checkKey?1000:0)+(goal&&row.goal===goal?30:0)+overlap(q,terms(`${row.hypothesis} ${row.command}`))}))
    .filter(x=>x.score>0||(!query&&!checkKey&&!goal)).sort((a,b)=>b.score-a.score||b.index-a.index).slice(0,limit)
    .map(({row})=>({...row,applicability:row.conditions.after===scope?'same_recorded_workspace_external_state_unverified':
      Object.entries(row.conditions.dependencies).some(([k,v])=>dependencies[k]!==undefined&&dependencies[k]!==v)?'dependencies_changed_recheck':'historical_conditions_recheck'}));
}

export function resultViews(rows,budget=2600) {
  const views=rows.map(r=>({id:r.id,evidence_id:r.evidence_id,anchor_ids:r.anchor_ids.slice(-4),
    hypothesis:r.hypothesis.slice(0,350),status:r.status,reason:r.reason,evidence:r.evidence,
    applicability:r.applicability,conditions:{before:r.conditions.before,after:r.conditions.after},
    next_use:r.next_use,semantic_verified:false,task_success:null,full_ref:'kz_history id=context'}));
  while(views.length>1&&JSON.stringify(views).length>budget)views.pop();
  return views;
}
