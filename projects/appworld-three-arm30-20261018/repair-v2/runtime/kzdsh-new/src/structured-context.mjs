import { nonempty } from './memory.mjs';
import { clip, extractStream, stageReceiptView } from './terminal.mjs';
import {resultViews} from './exploration-learning.mjs';
const FIELDS = ['facts','unresolved_issues','incomplete_plans','analysis_and_conclusions'];
const realEvidence=(evidence,id)=>typeof id==='string'&&/^E[1-9]\d*$/u.test(id)&&Object.hasOwn(evidence,id)&&evidence[id]?.id===id;
export class StructuredContext {
  constructor(state) { this.state = state ?? { facts: [], unresolved_issues: [], incomplete_plans: [], analysis_and_conclusions: [], retired: [] }; }
  update(update, evidence) {
    const copy = structuredClone(this.state);
    for (const f of FIELDS) for (const item of update[f] ?? []) {
      if (!item || !nonempty(item.text) || !Array.isArray(item.evidence_ids) || !item.evidence_ids.length || item.evidence_ids.some(id => !realEvidence(evidence,id))) throw new Error('context item needs text and real evidence IDs');
      if (!copy[f].some(x => x.text === item.text)) copy[f].push({ ...item, status: 'evidence_linked_model_claim' });
    }
    for (const change of update.retire ?? []) {
      const item = copy[change.field]?.find(x => x.text === change.text), row = evidence[change.evidence_id];
      if (!FIELDS.includes(change.field) || !item || !['resolved','invalidated'].includes(change.status) || !realEvidence(evidence,change.evidence_id) || !row?.complete || !nonempty(change.quote) || ![row.stdout,row.stderr].some(x => x.includes(change.quote))) throw new Error('retiring context requires an exact quote from complete evidence');
      copy[change.field] = copy[change.field].filter(x => x !== item); copy.retired.push({ ...change, semanticValidity: 'unverified' });
    }
    this.state = copy;
  }
}

export function buildContext(task, policy, maxChars = 24000, reserve = 8000) {
  const s = task.state;
  const recent = Object.values(s.evidence).sort((a,b)=>Number(a.id.slice(1))-Number(b.id.slice(1))).slice(-6).map(r => ({ id: r.id, command: clip(r.command,500), exitCode: r.exitCode, category: r.category, complete: r.complete,
    stdout: extractStream(r.stdout,r.category,1800), stderr: extractStream(r.stderr,r.category,1200), before: r.before, after: r.after, clean: r.clean, checkStatus: r.checkStatus, rawRef: r.rawRef,
    ...(r.shellStageReceipt?{shell_stages:stageReceiptView(r.shellStageReceipt)}:{}),
    ...(r.nativeToolError?{nativeToolError:true,commandExecuted:r.commandExecuted??null,status:'tool_error_observation_not_command_outcome'}:{}),
    ...(r.jobId?{jobId:r.jobId,jobStage:r.jobStage,jobStatus:r.jobStatus,launchEvidence:r.launchEvidence}: {}) }));
  const query = [s.taskGoal,policy.state.lastQuery,...recent.slice(-3).flatMap(r => [r.command,r.stderr,r.stdout])].join(' ');
  const recalled = task.memory.recall(query,s.scope,s.dependencies,task.config.recallLimit??4,s.urgent ?? []);
  const shown = [], omitted = [];
  for (const m of recalled) {
    const view = Object.fromEntries(['id','kind','conclusion','condition','operation','targets','next_step','evidence_ids','applicability','status','origin'].map(k => [k,m[k]]));
    if (JSON.stringify(view).length > reserve/4) {
      for(const field of ['conclusion','condition','operation','next_step'])view[field]=clip(String(view[field]??''),Math.floor(reserve/24));
      view.partial=true;view.full_ref=`kz_history id=${m.id}; read full conditional claim before relying on this excerpt`;
    }
    if (JSON.stringify([...shown,view]).length <= reserve) shown.push(view); else omitted.push(m.id);
  }
  s.visibleMemories = shown.map(x => x.id); s.visibleEvidence = recent.map(x => x.id);
  const reviewRequired=!policy.state.advisory&&policy.state.active;
  const focus=task.goals.view().focus;
  policy.state.focus={goal:task.goals.state.active,targets:focus?.targets??policy.state.focus.targets??[]};
  const result = { task: { originalGoalRef: s.taskInstruction?.path??'original user task in DSH session; not duplicated here', canonicalInstruction:s.taskInstruction??null },
    structured: structuredClone(task.context.state), subgoals: task.goals.view(),
    subgoal_controller:s.subgoalControl?{...s.subgoalControl,verification_candidates:s.subgoalControl.verification_candidates.map(({arguments:args,command,...rest})=>({...rest,command:clip(command,300),arguments_ref:rest.full_ref}))}:null,
    error_routes: { local: s.local, reconnaissance: task.config.reconnaissanceEnabled, critic: s.critic, backtracking:task.config.backtracking?'enabled':'frozen', checkpoints: s.checkpoints.map(x => ({ id:x.id,goals:x.goals })), rollback: s.pendingRollback },
    exploration: { active: policy.state.active, advisory: policy.state.advisory, episode:Object.fromEntries(['serial','executions','auxiliaryExecutions','rejections','cooldownRemaining','lastExit','trigger'].map(k=>[k,policy.state.episode[k]])), diagnostic:policy.state.diagnosticHint??null, negativeAnchors: policy.anchors(), results:resultViews(policy.explorationResults(s.scope,s.dependencies)), feedback: policy.state.lastFeedback,
      result_rule:'Statuses describe observed prediction matches under recorded conditions. They do not establish causality or task correctness. Reuse these observations when selecting the next probe, repair or verification.' },
    recovery_clock:{steps:task.clock.state.steps,executions:task.clock.state.executions,rejections:task.clock.state.rejections,recent_rejections:task.clock.state.controls.slice(-3).map(({id,kind,reason,clock})=>({id,kind,reason:clip(reason,500),clock})),instruction:'R records are rejected calls, not new environment results. They advance help scheduling, not failure memory.'},
    evidence: recent, completion:{status:s.completion?.status,gaps:(s.completion?.gaps??[]).filter(g=>g.status!=='closed').map(g=>({id:g.id,status:g.status,kind:g.kind,detail:clip(JSON.stringify(g.detail??''),600),next_step:g.next_step})),full_ref:'kz_history id=context'},
    monitor: s.monitor, advice:s.advice??null, notices: s.notices.slice(-4), delivery:s.delivery??null,budget:s.budgetView??null,
    background_jobs:{active_count:task.jobs.active().length,items:task.jobs.active().slice(-4).map(j=>({id:j.id,status:j.status,origin_call:j.call.callId,launch_evidence:j.launchEvidence})),instruction:'Use native job_output for output, not a duplicate launch. Running is not success; restored or incomplete output is unknown.'},
    diagnostic_nudge:task.advisory.state.diagnostics.length>=8?'Diagnosis has continued without file changes; this is not proof of failure. Name the remaining unknown, then choose a discriminating check or smallest justified repair.':null,
    memory_budget: { reserved_chars: reserve, omitted_ids: omitted }, memories: shown,
    memory_action_contract: { required:reviewRequired, visible_ids:s.visibleMemories,
      instruction:reviewRequired?'For gated actions, review applicability of matched memories and give exact native arguments via kz_strategy with execute:true to validate and execute in one tool call. Do not issue the same native command again after its receipt. Read-only reconnaissance and local corrections retain their exemptions. Native repairs need no orthogonality proof. Unchanged failed-command retry requires new related current-state support.':'No declaration is currently required (no active contract, or advisory mode). Use ordinary native tools directly; do not spend a separate request on an empty strategy declaration. Existing evidence remains relevant; host permissions and budgets still apply.',
      evidence_reference_rule:'Any real task-local E ID already observed may be cited, not only this display window. Archives are checked automatically; missing, foreign or future IDs are rejected. Historical evidence is not proof that the current state is unchanged.' } };
  result.structured.retired = result.structured.retired.slice(-2);
  const reserveUsed = JSON.stringify(shown).length;
  // Trim only displays. Full unresolved items and raw evidence remain in the task journal.
  result.displayOmissions = {};
  while (JSON.stringify(result).length > maxChars && result.evidence.length > 1) result.evidence.shift();
  for (const field of ['facts','analysis_and_conclusions','incomplete_plans','unresolved_issues']) {
    while (JSON.stringify(result).length > maxChars && result.structured[field].length) {
      result.structured[field].shift(); result.displayOmissions[field] = (result.displayOmissions[field] ?? 0) + 1;
    }
  }
  // Oversized prose is clipped in display only, never rejected or truncated at execution.
  if (JSON.stringify(result).length > maxChars) {
    for (const row of result.evidence) { row.stdout = clip(row.stdout,600); row.stderr = clip(row.stderr,600); }
    result.exploration.negativeAnchors = result.exploration.negativeAnchors.map(x => ({ id:x.id,outcome:x.outcome,command:clip(x.command,200) }));
    if (result.subgoals.focus) result.subgoals.focus = { id: result.subgoals.focus.id, detailRef: 'kz_history / task journal' };
  }
  if(JSON.stringify(result).length>maxChars) {
    result.error_routes={local:s.local?{kind:s.local.kind,remaining:s.local.remaining}:null,critic:{rounds:s.critic.rounds,decision:s.critic.decision},rollback:s.pendingRollback};
    result.monitor=s.monitor?{verdict:s.monitor.verdict,evidence_ids:s.monitor.evidence_ids,full_ref:'kz_history id=context'}:null;
    result.advice=s.advice?{full_ref:'kz_history id=context'}:null;
    result.notices=s.notices.slice(-2).map(x=>clip(x,300));
    result.exploration.feedback=policy.state.lastFeedback?{reason:clip(policy.state.lastFeedback.reason,400)}:null;
    result.subgoals.goals=result.subgoals.goals.map(({id,status,depends_on})=>({id,status,depends_on}));
    result.subgoals.notices=[];
    result.structured.retired=[];
    result.displayOmissions.full_details_ref='kz_history id=context';
  }
  if(JSON.stringify(result).length>maxChars) {
    result.evidence=[];result.exploration.negativeAnchors=[];
    result.structured={full_ref:'kz_history id=context',unresolved_count:task.context.state.unresolved_issues.length};
    result.delivery=s.delivery?{missing_count:s.delivery.missing.length,unverified_count:s.delivery.unverified.length,correctness:'unverified',full_ref:'kz_history id=context'}:null;
  }
  if(JSON.stringify(result).length>maxChars) {
    // Keep full plans/gaps in the ledger, not in every request. A compact
    // projection never changes scheduling, drops prerequisites or closes gaps.
    result.subgoals={active:task.goals.state.active,diagnostic_focus:task.goals.view().diagnostic_focus,
      total_goals:Object.keys(task.goals.state.items).length,full_ref:'kz_history id=context'};
    result.subgoal_controller=s.subgoalControl?{mode:s.subgoalControl.mode,active:s.subgoalControl.active,full_ref:'kz_history id=context'}:null;
    result.completion={status:s.completion?.status,open_gap_count:task.completion.open().length,full_ref:'kz_history id=context'};
    result.displayOmissions.plans_and_gaps='Full retained definitions and gap ledger are available via the context history reader.';
  }
  s.visibleEvidence = [...new Set([...result.evidence.map(x => x.id),...(s.retrievedEvidence??[]).filter(id=>s.evidence[id])])];
  return { text: JSON.stringify(result), reserveUsed, result };
}
