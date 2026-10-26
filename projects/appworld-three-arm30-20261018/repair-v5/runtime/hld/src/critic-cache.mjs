import {actionKey, stable} from './policy.mjs';
import {literalFileRead} from './commands.mjs';
import {knownDependency} from './memory.mjs';

// Session-local, explicit workspace-only checks. Never reuse on an unknown
// scope, after any intervening observation, or across a process/session restore.
export class CriticCache {
  constructor() {this.entries=new Map();}
  targets() {return [...new Set([...this.entries.values()].flatMap(x=>Object.keys(x.dependencies)))];}
  eligible(check,task) {
    if(check.cache_scope!=='workspace'||check.fresh===true||(check.fresh!==undefined&&typeof check.fresh!=='boolean'))return false;
    const key=actionKey({name:'bash',arguments:check.arguments});
    const goal=Object.values(task.goals.state.items).find(g=>g.definition.verification?.arguments&&actionKey({name:'bash',arguments:g.definition.verification.arguments})===key);
    return literalFileRead(check.arguments.command)||!!goal;
  }
  get(check,task) {
    if(!this.eligible(check,task))return null;
    const entry=this.entries.get(stable(check.arguments)),s=task.state;
    if(!entry||!s.scope?.startsWith('sha256:')||s.scope!==entry.scope||s.observed!==entry.observed||
        Object.keys(entry.dependencies).some(p=>!knownDependency(s.dependencies[p])||s.dependencies[p]!==entry.dependencies[p]))return null;
    return entry.row;
  }
  put(check,task,row) {
    if(!this.eligible(check,task)||!row?.complete||!row.clean||!row.before?.startsWith('sha256:')||row.before!==row.after||row.after!==task.state.scope)return;
    const dependencies=row.dependenciesAfter??{};
    if(!Object.keys(dependencies).length||Object.keys(dependencies).some(p=>!knownDependency(dependencies[p])||row.dependenciesBefore?.[p]!==dependencies[p]))return;
    this.entries.set(stable(check.arguments),{row:structuredClone(row),dependencies,scope:row.after,observed:task.state.observed});
    while(this.entries.size>4)this.entries.delete(this.entries.keys().next().value);
  }
}
