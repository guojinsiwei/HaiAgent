"""Build isolated exploration candidate; baseline and deployed tasks are untouched."""
from pathlib import Path
R=Path(__file__).parent/'candidate/src'
def edit(name,old,new):
    p=R/name;s=p.read_text(encoding='utf-8');assert old in s,(name,old[:100]);p.write_text(s.replace(old,new),encoding='utf-8')

edit('exploration-trigger.mjs',"  return JSON.stringify(['exact',directory,text.trim()]);",'''  // Test selection remains part of identity; cosmetic verbosity/output wrappers do not.
  // This projection only schedules exploration. Exact action admission is unchanged.
  if (!/[\\n\\r$`<>]/u.test(text)) {
    const test=text.match(/(?:^|[;&|]\\s*)(python(?:3)?\\s+-m\\s+pytest|pytest)\\s+([^;&|]*)/u);
    if(test) {
      const args=test[2].trim().split(/\\s+/u).filter(x=>x&&!/^(?:-q+|-v+|--tb=(?:short|long|no)|--disable-warnings|--no-header|--no-summary)$/u.test(x));
      if(args.length)return JSON.stringify(['pytest',directory,args]);
    }
  }
  return JSON.stringify(['exact',directory,text.trim()]);''')
edit('exploration-trigger.mjs',"export class ExplorationTrigger {",'''// Aggregate only failures sharing a declared goal, target set and diagnostic family.
// Unknown diagnostics remain exact; generic 'error' is deliberately insufficient.
export function issueIdentity(focus, observation, cwd='.') {
  const targets=[...new Set(focus?.targets??[])].filter(x=>typeof x==='string'&&x).sort();
  if(!focus?.goal||!targets.length)return null;
  const text=String(observation.stderr??'')+'\\n'+String(observation.stdout??'');
  const families=[...new Set(text.match(/\\b(?:[A-Z][A-Za-z]*(?:Error|Exception)|undefined reference|segmentation fault|connection refused|address already in use)\\b/gu)??[])].sort();
  if(!families.length)return null;
  return JSON.stringify(['issue',cwd,focus.goal,targets,families]);
}

export class ExplorationTrigger {''')
edit('exploration-trigger.mjs',"evidence in", "evidence in") if False else None
# Distinct ledgers can see the same receipt; a duplicate within a ledger cannot count twice.
edit('exploration-trigger.mjs',"this.state.seen.includes(evidence)","this.state.seen.includes(JSON.stringify([key,evidence]))||this.state.seen.includes(evidence)")
edit('exploration-trigger.mjs',"this.state.seen.push(evidence)","this.state.seen.push(JSON.stringify([key,evidence]))")

edit('policy.mjs',"ExplorationTrigger, checkIdentity", "ExplorationTrigger, checkIdentity, issueIdentity")
edit('policy.mjs',"explorationMaxExecutions: 8,", "explorationMaxExecutions: 8, explorationMaxTotalActions: 16,")
edit('policy.mjs',"'explorationMaxExecutions','explorationRejectLimit'", "'explorationMaxExecutions','explorationMaxTotalActions','explorationRejectLimit'")
edit('policy.mjs',"    this.learningEvents=[];", "    this.learningEvents=[];\n    this.state.monitorTriggers??=[];")
edit('policy.mjs',"    this.state.active=false;this.state.failureStreak=0;", "    this.learningEvents.push({event:'exploration_episode_end',...e.lastExit,task_success:null});\n    this.state.active=false;this.state.failureStreak=0;")
edit('policy.mjs',"    if(kind!=='probe'){e.auxiliaryExecutions++;return;}\n    e.executions++;", "    if(kind!=='probe')e.auxiliaryExecutions++;else e.executions++;\n    if(e.executions+e.auxiliaryExecutions>=this.config.explorationMaxTotalActions){this.endEpisode('total_action_window_complete');return;}\n    if(kind!=='probe')return;")
edit('policy.mjs',"    e.baselineKeys=this.state.memories.filter(r=>r.check_key===e.trigger.key).map(r=>r.key);", "    e.baselineKeys=this.state.memories.filter(r=>r.check_key===e.trigger.key||r.issue_key===e.trigger.key||e.trigger.evidence.includes(r.id)).map(r=>r.key);\n    this.learningEvents.push({event:'exploration_episode_start',serial:e.serial,trigger:e.trigger,baselineKeys:e.baselineKeys});")
edit('policy.mjs',"  recall(query = '') {",'''  observeMonitor(review,evidence) {
    if(!this.config.enabled||!this.config.explorationEnabled||review?.verdict!=='stalled')return false;
    const ids=[...new Set(review.evidence_ids??[])];
    // Control rejections alone never fabricate executed failure evidence.
    const rows=ids.map(id=>evidence[id]);
    if(ids.length<2||rows.some(r=>!r||!r.complete||r.nativeToolError||r.timedOut||r.aborted||r.blocked)||
       !rows.some(r=>r.failureObserved||r.exitCode!==undefined&&r.exitCode!==null&&r.exitCode!==0))return false;
    const latest=Math.max(0,...Object.keys(evidence).filter(id=>/^E\\d+$/u.test(id)).map(id=>Number(id.slice(1))));
    if(Math.max(...ids.map(id=>Number(id.slice(1))))<latest-6)return false;
    const signature=digest([...ids].sort());
    if(this.state.monitorTriggers.includes(signature))return false;
    if(this.state.active||this.state.episode.cooldownRemaining>0)return false;
    this.state.monitorTriggers.push(signature);this.state.monitorTriggers=this.state.monitorTriggers.slice(-64);
    const key=JSON.stringify(['monitor',this.state.focus.goal??null,signature]);
    for(const id of ids)this.trigger.observe(key,id,'failed');
    this.state.episode.rearmEvidence=true;
    this.activatePending(key);
    if(this.state.active){this.state.episode.trigger.reason='monitor_stalled_with_execution_evidence';
      this.state.diagnosticHint=review.next_check;return true;}
    return false;
  }
  recall(query = '') {''')
edit('policy.mjs',"      this.state.inflight[call.callId]={key:actionKey(call),kind,experiment:pending.exploration,", "      this.state.inflight[call.callId]={key:actionKey(call),kind,experiment:pending.exploration,result_decision:pending.result_decision??null,")
edit('policy.mjs',"    this.state.pending = structuredClone(proposal);",'''    if(proposal.result_decision) {
      const d=proposal.result_decision;
      if(!this.state.experiments.some(r=>r.id===d.result_id)||!['repair','verify','revise','retest','defer'].includes(d.action)||!nonempty(d.reason))
        return {accepted:false,reason:'Exploration follow-up needs a real result_id, action repair|verify|revise|retest|defer and brief reason.'};
    }
    const latest=this.state.experiments.filter(r=>r.episode===this.state.episode.serial).at(-1);
    if(this.state.active&&!bypassExploration&&proposal.exploration&&latest&&proposal.result_decision?.result_id!==latest.id)
      return {accepted:false,reason:`Exploration follow-up: use result_decision {result_id:"${latest.id}",action:"repair|verify|revise|retest|defer",reason:"how the result changes this action"}. A missing or ambiguous measurement needs a revised check.`};
    this.state.pending = structuredClone(proposal);''')
edit('policy.mjs',"/Active exploration requires|Exploration predictions/", "/Active exploration requires|Exploration predictions|Exploration follow-up|Submit kz_strategy/")
edit('policy.mjs',"    if (max > this.config.similarityThreshold) return this.deny('command_similarity_above_threshold', relevant[values.indexOf(max)].id);",'''    // Lexical similarity cannot tell a new boundary test from a repeated failed test.
    // Exact unchanged failures are already guarded above. A measured probe with a
    // declared changed dimension may proceed; retain similarity as audit telemetry.
    if (max > this.config.similarityThreshold && pending.exploration?.mode!=='metric')
      return this.deny('command_similarity_above_threshold', relevant[values.indexOf(max)].id);''')
edit('policy.mjs',"    if (!observation.complete || !Number.isInteger(observation.exitCode))", "    if (!observation.complete || observation.timedOut || observation.aborted || observation.blocked || observation.nativeToolError || !Number.isInteger(observation.exitCode))")
edit('policy.mjs',"    record.check_key=checkIdentity", "    record.issue_key=issueIdentity(this.state.focus,observation,call.arguments.workdir??'.');\n    record.check_key=checkIdentity")
edit('policy.mjs',"    const repeat=this.state.outputRepeat;\n    const interleaved=", "    if(!observation.noMatch&&outcome==='execution_failed'&&record.issue_key)this.trigger.observe(record.issue_key,record.id,'failed');\n    const repeat=this.state.outputRepeat;\n    const interleaved=")
edit('policy.mjs',"    this.activatePending(check);", "    this.activatePending(check);\n    if(record.issue_key)this.activatePending(record.issue_key);")
edit('policy.mjs',"    if (improved&&this.state.active) this.endEpisode('verified_command_improvement');", "    if (improved&&this.state.active&&this.state.episode.baselineKeys.includes(key)) this.endEpisode('verified_command_improvement');")
edit('full-integration.mjs',"e.full.acceptMonitor(review,supplied,controls);record", "e.full.acceptMonitor(review,supplied,controls);e.policy.observeMonitor(review,s.evidence);record")
edit('plugin.mjs',"orthogonal-learning-20261017", "orthogonal-measured-followup-20261018-v2")
print('Policy and triggers updated')
