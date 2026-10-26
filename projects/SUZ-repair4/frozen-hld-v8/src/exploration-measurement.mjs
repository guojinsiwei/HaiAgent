// Preregistered measurements are observations, never a semantic correctness oracle.
const nonempty=x=>typeof x==='string'&&x.trim().length>0;
const opposite={eq:'ne',ne:'eq',lt:'gte',gte:'lt',lte:'gt',gt:'lte'};
const numeric=new Set(['lt','lte','gt','gte']);
export function validateMeasurement(value) {
  if(!value||!nonempty(value.hypothesis))throw new Error('Active exploration requires an exploration hypothesis.');
  const a=value.supports,b=value.refutes;
  if(!a||!b)throw new Error('Exploration predictions need supports and refutes.');
  if(a.metric!==undefined||b.metric!==undefined) {
    for(const p of [a,b]) {
      if(!['stdout','stderr'].includes(p.field)||!nonempty(p.metric)||!/^[A-Za-z_][A-Za-z0-9_]{0,79}$/u.test(p.metric)||
         !Object.hasOwn(opposite,p.op)||!['number','boolean','string'].includes(typeof p.value)||
         typeof p.value==='number'&&!Number.isFinite(p.value)||numeric.has(p.op)&&typeof p.value!=='number')
        throw new Error('Exploration predictions need a JSON metric key, field stdout|stderr, op eq|ne|lt|lte|gt|gte and a matching finite value.');
    }
    if(a.field!==b.field||a.metric!==b.metric||a.op!==opposite[b.op]||a.value!==b.value)
      throw new Error('Exploration predictions must use complementary comparisons of the same metric and threshold.');
    if(!nonempty(value.alternative)||!nonempty(value.measurement))
      throw new Error('Exploration predictions need an alternative hypothesis and measurement describing how the value is computed from task behavior.');
    return {...value,mode:'metric',supports:{field:a.field,metric:a.metric,op:a.op,value:a.value},refutes:{field:b.field,metric:b.metric,op:b.op,value:b.value}};
  }
  for(const p of [a,b])if(!['stdout','stderr'].includes(p.field)||!nonempty(p.contains)||p.contains.length>240)
    throw new Error('Exploration predictions need field stdout|stderr and nonempty contains (max 240), or a measured JSON metric.');
  if(a.field===b.field&&(a.contains.includes(b.contains)||b.contains.includes(a.contains)))
    throw new Error('Exploration predictions must distinguish support from refutation.');
  return {...value,mode:'literal',supports:{field:a.field,contains:a.contains},refutes:{field:b.field,contains:b.contains}};
}
export function measure(experiment,out,usable) {
  if(!usable)return {status:'unknown',reason:'execution_unusable',evidence:[]};
  if(experiment.mode!=='metric') {
    const evidence=['supports','refutes'].filter(k=>String(out[experiment[k].field]??'').includes(experiment[k].contains))
      .map(k=>({field:experiment[k].field,quote:experiment[k].contains,matched_prediction:k}));
    return {status:'unknown',reason:evidence.length?'literal_observation_only':'no_predicted_observation',evidence};
  }
  const p=experiment.supports,values=[];
  for(const line of String(out[p.field]??'').split('\n')) {
    try {const row=JSON.parse(line);if(row&&typeof row==='object'&&!Array.isArray(row)&&Object.hasOwn(row,p.metric))values.push(row[p.metric]);}catch{}
  }
  if(!values.length)return {status:'unknown',reason:'missing_measurement',evidence:[]};
  // A JSON value is a measurement only if the complete receipt gives one unambiguous
  // scalar. Multiple test cases require the probe to compute a named aggregate.
  if(values.some(v=>typeof v!==typeof p.value||typeof v==='number'&&!Number.isFinite(v))||new Set(values.map(v=>JSON.stringify(v))).size!==1)
    return {status:'unknown',reason:'ambiguous_or_mistyped_measurement',evidence:[]};
  const v=values[0];
  const matched={eq:()=>v===p.value,ne:()=>v!==p.value,lt:()=>v<p.value,lte:()=>v<=p.value,gt:()=>v>p.value,gte:()=>v>=p.value}[p.op]();
  return {status:matched?'supported':'refuted',reason:'measured_prediction_match',
    evidence:[{field:p.field,metric:p.metric,value:v,op:p.op,threshold:p.value}],measurement:experiment.measurement,
    provenance:'solver_authored_measurement_semantics_unverified'};
}
