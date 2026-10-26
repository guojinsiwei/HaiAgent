// Task-local evidence-linked claims; observed facts and causal interpretation stay separate.
import { actionKey, digest, words } from './policy.mjs';
import { lstat, realpath } from 'node:fs/promises';
import path from 'node:path';
import { artifactTarget, checkArtifactPath } from './artifacts.mjs';
import {exactSupport} from './mechanism-evidence.mjs';
export const nonempty = value => typeof value === 'string' && !!value.trim() && !value.includes('\0');
export function relativeTarget(value) {
  if (!nonempty(value) || value.includes('\\') || value.startsWith('/') || /^[A-Za-z]:/u.test(value) || value.split('/').includes('..')) throw new Error('target must be a workspace-relative path');
  const result = value.replace(/^\.\//u, '').replace(/\/$/u, '');
  if (!result || result === '.' || result.split('/').includes('.git')) throw new Error('explicit task path required');
  return result;
}
export const knownDependency = value => typeof value === 'string' && /^(file:|dir:|missing$)/u.test(value);

// Resolve model-supplied paths only against an explicit task root. This is an
// admission helper, not permission to read targets or follow links outside it.
export async function normalizeMemoryTargets(candidate, workspaceRoot, {maxTargets=4}={}) {
  if (!candidate || !Array.isArray(candidate.targets ?? []) || (candidate.targets ?? []).length > maxTargets) throw new Error('at most four target paths');
  if (!path.isAbsolute(workspaceRoot ?? '')) throw new Error('memory normalization needs an explicit absolute workspace root');
  const root=await realpath(workspaceRoot);
  if (root===path.parse(root).root || !(await lstat(root)).isDirectory()) throw new Error('memory normalization needs a task directory');
  const targets=[];
  for (const raw of candidate.targets ?? []) {
    if (!nonempty(raw)) throw new Error('target must be a workspace-relative path');
    if(raw.split(/[\\/]/u).includes('..'))throw new Error('memory target must not traverse parent paths');
    const name=relativeTarget(artifactTarget(root,raw));
    await checkArtifactPath(root,name);
    targets.push(name);
  }
  return {...candidate,targets:[...new Set(targets)]};
}

// Correct only a channel-label mistake: preserve the exact quotation, and never
// search other IDs or infer/paraphrase missing text. Call this on the supplied
// monitor view first, then validate again against the raw evidence in admit().
export function normalizeMemorySupport(candidate, evidence) {
  if (!Array.isArray(candidate?.support)) throw new Error('monitor claims need exact quotes for every cited observation');
  const support=candidate.support.map(value=>{
    if (!value || typeof value!=='object' || !['stdout','stderr'].includes(value.field) || !nonempty(value.quote) || /omitted/iu.test(value.quote)) throw new Error('monitor claims need exact quotes for every cited observation');
    const row=evidence[value.evidence_id];
    const matches=['stdout','stderr'].filter(field=>typeof row?.[field]==='string'&&row[field].includes(value.quote));
    if (matches.includes(value.field)) return {...value};
    if (matches.length!==1) throw new Error('monitor claims need exact quotes for every cited observation');
    return {...value,field:matches[0],declared_field:value.declared_field??value.field};
  });
  return {...candidate,support};
}

export class TaskMemory {
  constructor(state, capacity = 24) { this.state = state ?? { next: 1, items: [], evicted: [] }; this.capacity = capacity; }
  applicability(item, scope, dependencies) {
    if(item.disputed)return 'disputed_claim_recheck_required';
    if (item.targets.length) return item.targets.every(p => knownDependency(dependencies[p]) && dependencies[p] === item.dependencies[p])
      ? 'target_dependencies_unchanged_external_state_unverified' : 'target_dependencies_changed_or_unknown_recheck_required';
    return scope?.startsWith('sha256:') && item.scopes.every(x => x === scope)
      ? 'same_workspace_external_state_unverified' : 'historical_recheck_required';
  }
  targets() { return [...new Set(this.state.items.flatMap(x => x.targets))]; }
  correct(value,evidence) {
    if(!value||!Array.isArray(value.ids)||!value.ids.length||!nonempty(value.reason)||!exactSupport(value.support,evidence))throw new Error('memory correction needs known IDs, reason and exact complete observation support');
    const items=value.ids.map(id=>this.state.items.find(m=>m.id===id));
    if(items.some(m=>!m))throw new Error('unknown memory correction ID');
    if(items.some(m=>!value.support.some(s=>Number(s.evidence_id.slice(1))>Math.max(...m.evidence_ids.map(id=>Number(id.slice(1)))))))throw new Error('memory correction requires newer observations');
    for(const m of items){m.disputed={reason:value.reason,support:structuredClone(value.support),status:'attributed_contradiction_requires_recheck'};m.status='disputed_claim_not_action_basis';}
    return {ids:value.ids,status:'disputed',evidence_ids:[...new Set(value.support.map(x=>x.evidence_id))]};
  }
  matchAction(call, scope, dependencies, targets = []) {
    const query=[call.name,call.arguments.command??'',call.arguments.description??'',...targets].join(' ').toLowerCase();
    const tokens=words(query);
    return this.state.items.filter(m=>{
      if(m.kind!=='blocker'||!/unchanged|^same_workspace/u.test(this.applicability(m,scope,dependencies)))return false;
      const targetHit=m.targets.some(p=>targets.includes(p)||tokens.has(p.toLowerCase())||tokens.has(p.split('/').at(-1).toLowerCase()));
      const operation=words(m.operation),operationHit=operation.size>0&&[...operation].every(x=>tokens.has(x));
      // Native edits have no CLI operation spelling. Matching their exact normalized
      // target requests a review, not a claim that modifying that file is forbidden.
      return m.commandKey===actionKey(call)||(targetHit&&(operationHit||['edit','write'].includes(call.name)));
    });
  }
  admit(candidate, evidence, visible, scope, dependencies, origin = 'solver') {
    if (!candidate || !['finding','blocker','procedure'].includes(candidate.kind) || !nonempty(candidate.conclusion) || !nonempty(candidate.condition)) throw new Error('memory needs kind, conclusion and condition');
    const ids = candidate.evidence_ids;
    if (!Array.isArray(ids) || !ids.length || ids.length > 3 || new Set(ids).size !== ids.length || ids.some(id => !visible.includes(id) || !evidence[id])) throw new Error('memory must cite 1–3 supplied evidence IDs');
    if (!Array.isArray(candidate.targets ?? []) || (candidate.targets ?? []).length > 4) throw new Error('at most four target paths');
    const targets = [...new Set((candidate.targets ?? []).map(relativeTarget))];
    const refs = ids.map(id => evidence[id]);
    if (refs.some(x => !x.complete)) throw new Error('incomplete evidence cannot support a durable lesson');
    const nativeError=refs.some(x=>x.nativeToolError);
    if (nativeError&&(candidate.kind==='blocker'||candidate.commandKey)) throw new Error('native tool errors support conditional findings/procedures, not failed command or route blockers');
    if (origin === 'monitor') {
      candidate=normalizeMemorySupport(candidate,evidence);
      const support = candidate.support;
      if (!Array.isArray(support) || !ids.every(id => support.some(s => s.evidence_id === id && ['stdout','stderr'].includes(s.field) && nonempty(s.quote) && !/omitted/iu.test(s.quote) && evidence[id][s.field].includes(s.quote)))) throw new Error('monitor claims need exact quotes for every cited observation');
    }
    const deps = Object.fromEntries(targets.map(p => {
      const values = refs.map(r => r.dependenciesAfter?.[p]);
      let value = values.at(-1);
      if (!values.every(x => knownDependency(x) && x === value)) value = refs.every(r => r.after === scope) ? dependencies[p] : 'unknown';
      return [p, knownDependency(value) ? value : 'unknown'];
    }));
    const identity = digest([candidate.kind, candidate.conclusion.toLowerCase(), candidate.condition.toLowerCase(), targets, deps, targets.length ? null : refs.at(-1).after]);
    const old = this.state.items.find(x => x.identity === identity);
    if (old) { old.evidence_ids = [...new Set([...old.evidence_ids,...ids])].slice(-3); old.reinforcements++; old.updated = this.state.next++; return old; }
    const item = { id: `M${this.state.next++}`, identity, kind: candidate.kind, conclusion: candidate.conclusion,
      condition: candidate.condition, operation: candidate.operation ?? '', next_step: candidate.next_step ?? '',
      targets, dependencies: deps, scopes: [...new Set(refs.map(r => r.after))], evidence_ids: ids,
      support: candidate.support ?? [], status: nativeError ? 'observed_native_tool_error_not_command_outcome' : origin === 'observer' ? 'observed_tool_outcome_not_causal_rule' : 'evidence_linked_model_claim_not_verified',
      claim_type:origin==='observer'?'tool_observation':['hypothesis','derived_measurement'].includes(candidate.claim_type)?candidate.claim_type:'model_interpretation',
      expected_basis:typeof candidate.expected_basis==='string'?candidate.expected_basis:null,
      origin, commandKey: candidate.commandKey ?? null, reinforcements: 1, updated: this.state.next };
    this.state.items.push(item);
    while (this.state.items.length > this.capacity) {
      const rank = x => [Number(/unchanged|^same_workspace/u.test(this.applicability(x, scope, dependencies))), Math.min(x.reinforcements,3),x.updated];
      const sorted = [...this.state.items].sort((a,b) => { const x=rank(a),y=rank(b); return x[0]-y[0] || x[1]-y[1] || x[2]-y[2]; });
      const victim = sorted[0]; this.state.items = this.state.items.filter(x => x !== victim); this.state.evicted.push(victim.id);
      this.state.evicted = this.state.evicted.slice(-24);
    }
    return item;
  }
  recall(query, scope, dependencies, limit = 4, urgent = []) {
    const q = words(query);
    return this.state.items.map(item => {
      const overlap = [...words([item.conclusion,item.condition,item.operation,item.next_step,...item.targets].join(' '))].filter(x => q.has(x)).length;
      const applicability = this.applicability(item, scope, dependencies);
      return { ...item, applicability, overlap, current: /unchanged|^same_workspace/u.test(applicability), urgent: urgent.includes(item.id) };
    }).filter(x => x.overlap || x.urgent).sort((a,b) => Number(b.urgent)-Number(a.urgent) || Number(b.current)-Number(a.current) || b.overlap-a.overlap || Math.min(b.reinforcements,3)-Math.min(a.reinforcements,3) || b.updated-a.updated).slice(0,limit);
  }
  review(value, visible) {
    if (!visible.length) return;
    if (!value || !Array.isArray(value.ids) || !value.ids.length || value.ids.some(id => !visible.includes(id))) throw new Error('memory_review must cite currently visible M IDs');
    if (!['apply','recheck','different_route','not_applicable','justified_retry'].includes(value.decision)) throw new Error('invalid memory decision');
    for (const key of ['observed_result','applicability','reason']) if (!nonempty(value[key])) throw new Error(`memory_review.${key} required`);
    if (value.decision === 'justified_retry' && !nonempty(value.new_evidence)) throw new Error('retry needs a changed condition or discriminating observation');
  }
}
