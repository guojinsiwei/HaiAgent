import { actionKey, commandIdentity, stable } from './policy.mjs';
import { relativeTarget, nonempty, knownDependency } from './memory.mjs';
import {verificationMatches} from './verification-identity.mjs';
const key = args => actionKey({ name: 'bash', arguments: args });
const updateFields = ['title','acceptance','depends_on','targets','verification'];
export function substantiveSilentCheck(args) {
  const identity=commandIdentity(args?.command??'');if(identity[0]!=='literal')return false;
  const executable=identity[1].split('/').at(-1),argv=identity[2];
  if(argv.some(value=>['--help','-h','--version','-V','--collect-only','--collectonly','--co','--list-tests','--list','--listTests','--showConfig','--fixtures','--fixtures-per-test','--setup-plan','--dry-run','--no-run'].includes(value)))return false;
  if(executable==='make'&&argv.some(value=>/^-[^-]*[nq]/u.test(value)||['--just-print','--recon','--question'].includes(value)))return false;
  if(executable==='ctest'&&argv.some(value=>/^-[^-]*N/u.test(value)||/^--show-only(?:=|$)/u.test(value)))return false;
  if(executable==='go'&&argv.some(value=>/^-{1,2}list(?:=|$)/u.test(value)||['-n','-c'].includes(value)))return false;
  if(['pytest','py.test','ctest'].includes(executable))return true;
  if(/^python[\d.]*$/u.test(executable)) {
    const rest=[...argv];
    while(rest.length&&/^-[BuEIs]+$/u.test(rest[0]))rest.shift();
    if(rest[0]==='-m'&&['doctest','unittest','pytest'].includes(rest[1]))return rest[1]!=='doctest'||
      !rest.slice(2).some(value=>value==='SKIP'||value==='-oSKIP'||value==='--option=SKIP')&&rest.slice(2).some(value=>!value.startsWith('-'));
  }
  if(executable==='node'&&argv.includes('--test'))return true;
  if(['npm','pnpm','yarn','cargo','go','make'].includes(executable)&&argv[0]==='test')return true;
  return false;
}
function definition(raw) {
  if (!raw || !/^G[1-9]\d{0,2}$/u.test(raw.id) || !nonempty(raw.title) || !nonempty(raw.acceptance)) throw new Error('subgoal needs stable G ID, title and public acceptance criterion');
  if (!Array.isArray(raw.depends_on) || !Array.isArray(raw.targets)) throw new Error('subgoal needs dependency and target arrays');
  // A useful plan can precede discovering the exact public verification command.
  // Until that command is registered, no observation can mark the goal passed.
  if (raw.verification != null) {
    const verification=raw.verification;
    if (!nonempty(verification.arguments?.command) || !Array.isArray(verification.stdout_contains) || verification.stdout_contains.some(x => !nonempty(x))) throw new Error('declare an executable public check and output assertions, or explicit exit_code:0 for a recognized silent substantive test');
    if (verification.exit_code!==undefined&&verification.exit_code!==0)throw new Error('subgoal verification must require exit_code:0');
    if (/^(?:echo|true|printf|:)(?:\s|$)/u.test(verification.arguments.command.trim())) throw new Error('a trivial marker is not a verification');
    if (!verification.stdout_contains.length&&(verification.exit_code!==0||!substantiveSilentCheck(verification.arguments)))throw new Error('empty output assertions require explicit exit_code:0 and a recognized substantive public test, not a generic zero-exit command');
  }
  return { ...structuredClone(raw), targets: [...new Set(raw.targets.map(relativeTarget))] };
}
export class Subgoals {
  constructor(state) {
    this.state = state ?? { items: {}, active: null, notices: [] };
    for (const item of Object.values(this.state.items)) {
      const legacy=item.revision===undefined;item.revision??=1;item.history??=[];
      if(legacy&&item.proof&&item.proof.revision===undefined)item.proof.revision=1;
    }
  }
  admit(metadata) {
    const warnings=[],accepted=[];
    if(metadata.subgoal_plan!==undefined&&!Array.isArray(metadata.subgoal_plan))throw new Error('subgoal_plan must be an array');
    for(const raw of metadata.subgoal_plan??[]) {
      let value;
      try{value=definition(raw);}catch(error){
        // A bad checker must not erase a sound goal. Never repair its command.
        try{value=definition({...raw,verification:undefined});warnings.push({id:raw.id,field:'verification',reason:error.message});}
        catch{this.state.drafts??=[];this.state.drafts.push({value:raw,reason:error.message});warnings.push({id:raw?.id,field:'definition',reason:error.message});continue;}
      }
      const old=this.state.items[value.id];
      if(old&&stable(old.definition)!==stable(value)){warnings.push({id:value.id,reason:'use explicit subgoal_update to change an existing goal'});continue;}
      this.state.items[value.id]??={definition:value,revision:1,history:[],status:'pending',checks:0,proof:null,lastEvidence:null};accepted.push(value.id);
    }
    if(metadata.subgoal_update) {
      const u=metadata.subgoal_update,item=this.state.items[u.id];
      try{
        if(!item||!nonempty(u.reason))throw new Error('update needs a known goal and reason');
        if(u.expected_revision!==undefined&&u.expected_revision!==item.revision)throw new Error('stale subgoal revision');
        if(u.status!==undefined&&!['pending','blocked','deferred'].includes(u.status))throw new Error('model cannot self-declare a passing goal');
        const patch=Object.fromEntries(updateFields.filter(k=>Object.hasOwn(u,k)).map(k=>[k,u[k]]));
        if(!Object.keys(patch).length&&u.status===undefined)throw new Error('update needs a definition or status change');
        let value;
        try{value=definition({...item.definition,...patch});}catch(error){
          if(!Object.hasOwn(patch,'verification'))throw error;
          value=definition({...item.definition,...patch,verification:undefined});warnings.push({id:u.id,field:'verification',reason:error.message});
        }
        if(stable(value)!==stable(item.definition)) {
          item.history.push({revision:item.revision,definition:item.definition,proof:item.proof,reason:u.reason});
          item.definition=value;item.revision++;item.proof=null;item.status=u.status??'pending';
        }else if(u.status){item.status=u.status;item.proof=null;}
        accepted.push(u.id);
      }catch(error){warnings.push({id:u.id,field:'update',reason:error.message});}
    }
    const resolved=new Map();
    const problem=(id,stack=new Set())=>{
      if(resolved.has(id))return resolved.get(id);
      const item=this.state.items[id];if(!item)return 'missing_prerequisite';
      if(stack.has(id))return 'dependency_cycle';
      for(const dependency of item.definition.depends_on){const result=problem(dependency,new Set([...stack,id]));if(result){resolved.set(id,result);return result;}}
      resolved.set(id,null);return null;
    };
    for(const [id,item] of Object.entries(this.state.items)) {
      item.dependencyProblem=problem(id);
      if(item.dependencyProblem&&item.status==='check_passed'){item.status='needs_recheck';item.proof=null;}
    }
    if(metadata.subgoal_id&&this.state.items[metadata.subgoal_id])this.state.active=metadata.subgoal_id;
    if(!Object.keys(this.state.items).length)this.state.rootGoal={id:'TASK_ROOT',status:'plan_missing',acceptance:'Original public task; not a verified decomposition'};
    else delete this.state.rootGoal;
    this.state.notices=warnings.map(x=>`${x.id??'draft'}: ${x.reason}`);this.invalidateDependents();this.advanceFocus();
    return warnings.length?{status:'partial',accepted,warnings,known_goal_ids:Object.keys(this.state.items),active:this.state.active}:'accepted';
  }
  define(metadata) {
    // Atomic, optional sidecar: caller reports mistakes but never rejects an executable.
    const copy = structuredClone(this.state), plan = metadata.subgoal_plan ?? [];
    if (!Array.isArray(plan)) throw new Error('subgoal definitions must be an array');
    for (const raw of plan) {
      const value = definition(raw);
      if (copy.items[raw.id] && stable(copy.items[raw.id].definition) !== stable(value)) throw new Error('existing subgoal definition is immutable through subgoal_plan; use explicit subgoal_update with a reason');
      copy.items[raw.id] ??= { definition: value, revision: 1, history: [], status: 'pending', checks: 0, proof: null, lastEvidence: null };
    }
    if (metadata.subgoal_update) {
      const u = metadata.subgoal_update, item = copy.items[u.id];
      if (!item || !nonempty(u.reason) || (u.status !== undefined && !['pending','blocked','deferred'].includes(u.status))) throw new Error('model may not mark a goal passed; updates need a known goal and reason');
      if (u.expected_revision !== undefined && u.expected_revision !== item.revision) throw new Error('stale subgoal revision; inspect the current definition before updating');
      const patch = Object.fromEntries(updateFields.filter(field => Object.hasOwn(u,field)).map(field => [field,u[field]]));
      if (!Object.keys(patch).length && u.status === undefined) throw new Error('subgoal update needs a definition change or pending/blocked/deferred status');
      const value = definition({ ...item.definition, ...patch });
      if (stable(value) !== stable(item.definition)) {
        item.history.push({ revision: item.revision, definition: item.definition, status: item.status, proof: item.proof, reason: u.reason });
        item.definition = value; item.revision++; item.status = u.status ?? 'pending'; item.proof = null;
      } else if (u.status !== undefined) { item.status = u.status; item.proof = null; }
      item.reason = u.reason;
    }
    const visited = new Set(), visiting = new Set();
    const visit = id => {
      if (!copy.items[id]) throw new Error('unknown prerequisite');
      if (visiting.has(id)) throw new Error('cyclic subgoal graph');
      if (visited.has(id)) return;
      visiting.add(id); for (const d of copy.items[id].definition.depends_on) visit(d);
      visiting.delete(id); visited.add(id);
    };
    Object.keys(copy.items).forEach(visit);
    if (metadata.subgoal_id !== undefined) {
      if (!copy.items[metadata.subgoal_id]) throw new Error('unknown focused goal');
      copy.active = metadata.subgoal_id;
    }
    copy.notices = []; this.state = copy; this.invalidateDependents(); this.advanceFocus();
  }
  targets() { return [...new Set(Object.values(this.state.items).flatMap(x => x.definition.targets))]; }
  unmet(id) { return this.state.items[id].definition.depends_on.filter(d => this.state.items[d]?.status !== 'check_passed'); }
  invalidateDependents() {
    for (let n = 0; n < Object.keys(this.state.items).length; n++) for (const [id,item] of Object.entries(this.state.items))
      if (item.status === 'check_passed' && this.unmet(id).length) { item.status = 'needs_recheck'; item.reason = 'prerequisite_not_current'; item.proof = null; }
  }
  sync(dependencies, restored = false) {
    for (const item of Object.values(this.state.items)) if (item.status === 'check_passed' && (restored || !item.proof || item.proof.revision!==item.revision || item.definition.targets.some(p => !knownDependency(dependencies[p]) || dependencies[p] !== item.proof.dependencies[p]))) {
      item.status = 'needs_recheck'; item.reason = restored ? 'restored_state_requires_recheck' : 'target_changed_or_unknown'; item.proof = null;
    }
    this.invalidateDependents(); this.advanceFocus();
  }
  observe(row) {
    const results = [];
    for (const [id,item] of Object.entries(this.state.items)) {
      if (['blocked','deferred'].includes(item.status)) continue;
      if (!item.definition.verification) continue;
      if (!verificationMatches(item.definition.verification.arguments,row)) continue;
      results.push(this.recordCheck(id,row,row.dependenciesAfter));
    }
    this.invalidateDependents(); this.advanceFocus(); return results;
  }
  recordCheck(id,row,currentDependencies) {
    const item = this.state.items[id];
    const stableTargets = item.definition.targets.length>0&&item.definition.targets.every(p => knownDependency(row.dependenciesAfter?.[p]) && row.dependenciesBefore?.[p] === row.dependenciesAfter[p] && currentDependencies?.[p] === row.dependenciesAfter[p]);
    const passed = !item.dependencyProblem&&row.clean===true && row.complete===true && row.executed===true && row.exitCode===0 && !row.nativeToolError && stableTargets && !this.unmet(id).length && item.definition.verification.stdout_contains.every(marker => row.stdout?.includes(marker));
    const assessment = `${item.revision}:${row.id}`;
    item.status = passed ? 'check_passed' : 'needs_work';
    if (item.lastAssessment !== assessment) item.checks++;
    item.lastAssessment = assessment; item.lastEvidence = row.id;
    item.reason = passed ? 'verified_current_execution' : !stableTargets ? 'target_changed_or_unknown' : this.unmet(id).length ? 'prerequisite_not_current' : 'check_not_clean_or_assertion_missing';
    item.proof = passed ? { revision: item.revision, evidence: row.id, scope: row.after, dependencies: Object.fromEntries(item.definition.targets.map(p => [p,row.dependenciesAfter[p]])) } : null;
    return { id, passed, stableTargets, revision: item.revision, definition: item.definition };
  }
  bindVerification(binding,evidence,currentDependencies) {
    const id = binding?.subgoal_id, item = this.state.items[id];
    if (!item || binding.revision !== item.revision) throw new Error('verification binding needs a known subgoal_id and its current revision');
    if (['blocked','deferred'].includes(item.status)) throw new Error('explicitly return a blocked/deferred goal to pending before binding verification');
    if (!item.definition.verification) throw new Error('register an explicit verification definition before binding evidence');
    const row = evidence?.[binding.evidence_id];
    if (!row || row.id !== binding.evidence_id || row.tool !== 'bash' || row.executed !== true || row.complete !== true || !Number.isInteger(row.exitCode) || (row.jobStage && row.jobStage !== 'final')) throw new Error('verification binding needs complete actual bash execution evidence');
    if (!verificationMatches(item.definition.verification.arguments,row)) throw new Error('evidence command does not match the current verification; explicitly update the definition before binding');
    if (Object.values(evidence).some(later => Number(later.id?.slice(1)) > Number(row.id.slice(1)) && verificationMatches(item.definition.verification.arguments,later) && later.executed === true && later.complete === true)) throw new Error('a later execution of this verification exists; bind its current result instead');
    // A caller passes trusted harness evidence and fresh target fingerprints, not
    // a model-supplied pass flag. The exact executed command remains auditable.
    this.sync(currentDependencies ?? {});
    if (item.proof?.evidence === row.id && item.proof.revision === item.revision && item.status === 'check_passed') return { id, passed: true, stableTargets: true, revision: item.revision, duplicate: true, definition: item.definition };
    const result = this.recordCheck(id,row,currentDependencies); this.invalidateDependents(); this.advanceFocus(); return result;
  }
  frontier() {
    const items = this.state.items, ready = Object.keys(items).filter(id => !items[id].dependencyProblem&&!['check_passed','blocked','deferred'].includes(items[id].status) && !this.unmet(id).length);
    const descendants = id => { const reached = new Set([id]); for (const _ of Object.keys(items)) for (const [k,r] of Object.entries(items)) if (r.definition.depends_on.some(d => reached.has(d))) reached.add(k); return reached.size; };
    const priority = id => ({needs_recheck:2,needs_work:1}[items[id].status]??0);
    ready.sort((a,b)=>priority(b)-priority(a)||descendants(b)-descendants(a)||Number(a.slice(1))-Number(b.slice(1)));
    const preferred = ready.includes(this.state.active) && priority(this.state.active) === priority(ready[0]);
    return { ready, suggested:preferred?this.state.active:ready[0]??null };
  }
  advanceFocus() {
    const previous=this.state.active,{suggested,ready}=this.frontier();this.state.active=suggested;
    return {previous,active:suggested,ready,changed:previous!==suggested};
  }
  view() {
    const items=this.state.items,{suggested,ready}=this.frontier();
    return { active: this.state.active, suggested, root_goal:this.state.rootGoal??null,
      diagnostic_focus:!suggested?Object.keys(items).find(id=>items[id].dependencyProblem)??null:null,
      diagnostic_instruction:'Resolve dependency cycles or missing prerequisite definitions; a diagnostic focus is not execution permission or a passed prerequisite.',
      goals: Object.entries(items).map(([id,x]) => ({ id, title: x.definition.title, status: x.status, dependency_unresolved:x.dependencyProblem??null, revision:x.revision, verification_status:x.definition.verification?'defined':'awaiting_definition', depends_on: x.definition.depends_on, evidence: x.lastEvidence })),
      ready, focus: suggested ? items[suggested].definition : null, notices: this.state.notices, taskSuccess: null };
  }
}
