from pathlib import Path
R=Path(__file__).parent/'candidate/src'
def edit(name,old,new):
    p=R/name;s=p.read_text();assert old in s,(name,old[:100]);p.write_text(s.replace(old,new))
p=R/'exploration-learning.mjs';s=p.read_text();a=s.index('export function validateExperiment');b=s.index('\nexport function selectAnchors',a)
s="import {validateMeasurement,measure} from './exploration-measurement.mjs';\n"+s[:a]+"export const validateExperiment=validateMeasurement;\n"+s[b:]
s=s.replace('(row.check_key===triggerKey&&triggerKey?1000:0)', '((row.check_key===triggerKey||row.issue_key===triggerKey)&&triggerKey?1000:0)')
a=s.index('  const matches=k=>');b=s.index('  return {id:`X${id}`',a)
s=s[:a]+"  const measured=measure(plan.experiment,out,usable);\n  const {status,evidence}=measured;\n"+s[b:]
a=s.index("    status,reason:!usable?");b=s.index('    semantic_verified:',a)
s=s[:a]+"    ...measured,evidence,conditions:{before,after,dependencies:{...dependencies}},\n    alternative:plan.experiment.alternative??null,result_decision:plan.result_decision??null,\n"+s[b:]
s=s.replace("'This attempt did not distinguish the hypothesis; inspect the failure or choose a different observation.'", "'This attempt did not distinguish the hypothesis. Inspect missing/ambiguous measurements, then revise the check; a printed filename or error label cannot establish the cause.'")
s=s.replace("hypothesis:r.hypothesis.slice(0,350),status", "hypothesis:r.hypothesis.slice(0,350),alternative:r.alternative??null,measurement:r.measurement??null,status")
p.write_text(s)

edit('policy.mjs',"    if(!observation.noMatch&&outcome==='execution_failed'&&record.issue_key)", "    if(improved&&prior?.issue_key)this.trigger.observe(prior.issue_key,record.id,'passed');\n    if(!observation.noMatch&&outcome==='execution_failed'&&record.issue_key)")
edit('policy.mjs',"    this.learningEvents.push({event:'exploration_learning',record:row});", "    this.learningEvents.push({event:'exploration_learning',record:row});\n    if(plan.result_decision)this.learningEvents.push({event:'exploration_result_used',decision:plan.result_decision,evidence_id:id,execution_complete:out.complete===true,workspace_changed:before!==after,task_success:null});")
# Capture explicit use on actual native repairs/verifications as well as probes.
edit('policy.mjs',"    this.state.admissions[call.callId]={kind};", "    this.state.admissions[call.callId]={kind};\n    if(pending?.result_decision)this.learningEvents.push({event:'exploration_followup_admitted',callId:call.callId,decision:pending.result_decision,tool:call.name,arguments:call.arguments});")

edit('plugin.mjs',"const strategySchema = {",'''const predictionSchema={type:'object',additionalProperties:false,properties:{
  field:{type:'string',enum:['stdout','stderr']},contains:{type:'string',minLength:1,maxLength:240},
  metric:{type:'string',pattern:'^[A-Za-z_][A-Za-z0-9_]{0,79}$'},op:{type:'string',enum:['eq','ne','lt','lte','gt','gte']},
  value:{type:['number','boolean','string']}},required:['field']};
const strategySchema = {''')
p=R/'plugin.mjs';s=p.read_text();a=s.index("    exploration:{type:");b=s.index("    orthogonality_proof:",a)
s=s[:a]+'''    exploration:{type:'object',additionalProperties:false,properties:{hypothesis:text,alternative:text,measurement:text,
      supports:predictionSchema,refutes:predictionSchema},required:['hypothesis','supports','refutes']},
    result_decision:{type:'object',additionalProperties:false,properties:{result_id:text,
      action:{type:'string',enum:['repair','verify','revise','retest','defer']},reason:text},required:['result_id','action','reason']},
'''+s[b:]
a=s.index('Include exploration:{hypothesis:');b=s.index('Prefer execute:true',a)
s=s[:a]+'''Use a small discriminating experiment in that SAME call. State the competing explanations,
what one observation can distinguish, and how the next action depends on that observation.
Example exploration:{hypothesis:"the boundary value is dropped",alternative:"both boundary and interior values are retained",
measurement:"run the public API on the boundary and an interior control, count missing results",
supports:{field:"stdout",metric:"missing_results",op:"gt",value:0},
refutes:{field:"stdout",metric:"missing_results",op:"lte",value:0}}.
The executed probe computes and prints a JSON line such as {"missing_results":n} from
actual task behavior. Never hardcode n, infer a cause from an error label, or print
invented success markers. Include one named aggregate per metric. Missing, conflicting,
incomplete or mistyped results remain unknown. Legacy contains predictions remain
observation-only; they cannot support or refute a hypothesis.
Read exploration.results before the next probe. Include result_decision:{result_id:"XE3",
action:"repair|verify|revise|retest|defer",reason:"how that observation changes this action"}
for the latest result in this episode. Use the actual result ID. A refuted hypothesis
calls for a revision or a specific changed condition. An unknown result calls for a
better measurement. A supported observation guides a repair and then the original
check. Measurement semantics and causal interpretation remain unverified.
Ordinary native reads, edits and post-repair checks need no exploration form. They can
optionally cite result_decision in kz_strategy. An episode lasts at most eight probes
or sixteen total native actions, then four recovery steps of cooldown. Two rejected
exploration declarations also end the gate; task execution continues.
'''+s[b:]
p.write_text(s)
p=R/'full-integration.mjs';s=p.read_text();a=s.index('By default an exploration episode ends');b=s.index('\nBefore ending,',a)
s=s[:a]+'''Exploration starts on repeated failed checks, failed probes sharing a declared goal/targets/diagnostic family, or Monitor stagnation supported by at least two recent complete execution observations including a failure. Trigger grouping never permits caching or rejecting distinct actions as equivalent.
An episode ends after eight probes, sixteen total native actions, or two exploration-format rejections, followed by four recovery steps of cooldown. Ordinary reads, repairs and changed-input verification stay available. Use measured JSON predictions and explicitly connect the next probe to the latest exploration result through result_decision. Lexical similarity is audit telemetry for measured probes; identical unchanged failed actions still require new evidence or relevant changed conditions. No rejection limit terminates the task.
''' + s[b:];p.write_text(s)
edit('structured-context.mjs',"['serial','executions','auxiliaryExecutions','rejections','cooldownRemaining','lastExit']", "['serial','executions','auxiliaryExecutions','rejections','cooldownRemaining','lastExit','trigger']")
print('Measured predictions, follow-up decisions and tool schema updated')
