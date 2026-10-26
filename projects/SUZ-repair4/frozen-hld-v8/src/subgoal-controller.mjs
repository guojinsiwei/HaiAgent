import { actionKey, commandIdentity } from './policy.mjs';
import { knownDependency } from './memory.mjs';
import { clip } from './terminal.mjs';
import { substantiveSilentCheck } from './subgoals.mjs';

const exactKey = args => actionKey({name:'bash',arguments:args});
const ordinal = row => Number(row.id?.slice(1))||0;
const planningNotice = 'Establish concrete subgoals from PUBLIC requirements: stable G IDs, public acceptance criteria, relevant task targets and depends_on edges. Keep all prerequisites and one ready focus; do not discard the tail of a plan. Verification may be omitted until discovered, but the goal stays unverified. Attach subgoal_plan to an action or use kz_update without a separate planner request. Do not invent a passing result. This does not block ordinary tools.';

function verificationCandidates(goals,evidence,dependencies) {
  const active=goals.state.active,item=goals.state.items[active];
  if(!item||!['pending','needs_work','needs_recheck'].includes(item.status))return [];
  const currentKey=item.definition.verification?exactKey(item.definition.verification.arguments):null;
  const rows=Object.values(evidence??{}).sort((a,b)=>ordinal(b)-ordinal(a)),seen=new Set(),result=[];
  for(const row of rows) {
    // A newer execution supersedes an old clean result, including a failure.
    if(!row.key||seen.has(row.key))continue;seen.add(row.key);
    if(row.tool!=='bash'||row.executed!==true||row.complete!==true||row.exitCode!==0||row.clean!==true||row.nativeToolError||row.suspect||row.jobStage&&row.jobStage!=='final')continue;
    const identity=commandIdentity(row.command??''),executable=identity[0]==='literal'?identity[1].split('/').at(-1):null;
    if(['echo','true','printf',':','cat','head','tail','grep','rg','sed','pwd','ls','find','wc','stat','file'].includes(executable))continue;
    const exactRegistered=currentKey!==null&&currentKey===row.key;
    // Output saying "PASS" does not turn cat/grep/echo into a public check.
    if(!['test','build'].includes(row.category)&&!exactRegistered&&!substantiveSilentCheck(row.arguments??{command:row.command}))continue;
    if(!item.definition.targets.every(target=>knownDependency(dependencies?.[target])&&row.dependenciesBefore?.[target]===dependencies[target]&&row.dependenciesAfter?.[target]===dependencies[target]))continue;
    if(item.proof?.evidence===row.id&&item.proof.revision===item.revision)continue;
    const actualArguments=row.arguments&&typeof row.arguments.command==='string'&&exactKey(row.arguments)===row.key?structuredClone(row.arguments):null;
    result.push({subgoal_id:active,revision:item.revision,evidence_id:row.id,command:row.command,
      ...(actualArguments?{arguments:actualArguments}:{arguments_unavailable:true}),
      stdout_excerpt:clip(String(row.stdout??''),360),stderr_excerpt:clip(String(row.stderr??''),180),
      exact_registered_check:exactRegistered,coverage:'unverified; decide whether this actual public check covers the goal acceptance',
      full_ref:`kz_history id=${row.id}`});
    if(result.length===2)break;
  }
  return result;
}

// Deterministic scheduling and reminders only: no model calls, execution, budget
// overrides, fabricated goals, or semantic auto-passing of test candidates.
export class SubgoalController {
  constructor(state) {
    this.state=state??{version:1,planPrompts:0,lastPlanObserved:0,lastPlanRequests:0,lastActive:null,candidateSignatures:{},ticks:0};
    if(this.state.version!==1)throw new Error('unsupported subgoal controller checkpoint');
    this.state.candidateSignatures??={};
  }
  tick(goals,{evidence={},dependencies={},observed=0,requests=0}={}) {
    goals.sync(dependencies);const focus=goals.advanceFocus(),events=[],notices=[];
    this.state.ticks++;
    const items=Object.values(goals.state.items),missingPlan=items.length===0;
    if(missingPlan&&this.state.planPrompts<2&&(this.state.planPrompts===0||observed-this.state.lastPlanObserved>=3||requests-this.state.lastPlanRequests>=3)) {
      this.state.planPrompts++;this.state.lastPlanObserved=observed;this.state.lastPlanRequests=requests;
      notices.push(planningNotice);events.push({event:'subgoal_plan_requested',attempt:this.state.planPrompts,blocking:false});
    }
    if(this.state.lastActive!==focus.active) {
      events.push({event:'subgoal_focus_changed',previous:this.state.lastActive,active:focus.active,ready:focus.ready});
      this.state.lastActive=focus.active;
    }
    const candidates=verificationCandidates(goals,evidence,dependencies),fresh=[];
    for(const candidate of candidates) {
      const signature=`${candidate.revision}:${candidate.evidence_id}`;
      const key=`${candidate.subgoal_id}:${candidate.evidence_id}`;
      if(this.state.candidateSignatures[key]===signature)continue;
      this.state.candidateSignatures[key]=signature;fresh.push(candidate);
    }
    // IDs track audit hints, not memory admission. Bound the hint ledger without
    // deleting goals, their definitions, or execution evidence.
    const ids=Object.keys(this.state.candidateSignatures);
    for(const id of ids.slice(0,Math.max(0,ids.length-96)))delete this.state.candidateSignatures[id];
    if(fresh.length) {
      notices.push('Actual clean public-check candidates are available: '+JSON.stringify(fresh)+'. Coverage is NOT automatic. Inspect exact output/arguments and current goal criteria. If appropriate, explicitly update verification with the real native arguments and exact output assertions, then bind verification_evidence to that revision in the same kz_update or kz_strategy. A recognized silent substantive test such as python -m doctest may explicitly use exit_code:0 and stdout_contains:[]; do not invent a success marker. If legacy evidence lacks full arguments, inspect the archive; do not guess missing arguments. Do not mark the goal passed yourself.');
      events.push({event:'subgoal_verification_candidates',candidates:fresh,automatic_pass:false});
    }
    const diagnostic=goals.view().diagnostic_focus;
    if(diagnostic)notices.push(`Dependency graph unresolved at ${diagnostic}. Inspect/correct its prerequisite definitions; do not execute it as though prerequisites passed.`);
    const unresolved=items.filter(item=>item.status!=='check_passed').length;
    return {events,notice:notices.length?notices.join('\n'):null,view:{mode:missingPlan?'plan_needed':focus.active?'working':unresolved?'blocked_or_deferred':'planned_checks_passed',
      active:focus.active,diagnostic_focus:diagnostic,dependency_unresolved:!!diagnostic,ready:focus.ready,plan_requests:this.state.planPrompts,plan_request_limit:2,unresolved,
      verification_candidates:candidates,blocking:false,official_success:null,
      instruction:focus.active?'Work on the active ready goal; public verification advances the frontier. New failures or changed targets invalidate prior proof.':missingPlan?'Create concrete goals while continuing useful work; no execution is blocked for a missing plan.':unresolved?'No ready active goal. Inspect blocked/deferred goals and missing prerequisites; explicitly revise only when justified.':'Registered goal checks are current; this does not establish official task success.'}};
  }
}
