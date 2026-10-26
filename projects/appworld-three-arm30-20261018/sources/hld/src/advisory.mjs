import { digest } from './policy.mjs';

const known = scope => typeof scope==='string' && scope.startsWith('sha256:');
const priority = { extended_diagnosis:1, repeated_failure:2, rejection_stall:3, semantic_stall:3 };

// Task-local scheduling only. Never executes commands or grants new budgets.
export class Advisory {
  constructor(state,config) {
    this.state=state??{pending:null,attempted:[],failureSignature:null,failures:[],diagnostics:[],events:[]};
    this.config={repeatedFailureThreshold:3,diagnosticAdvisorThreshold:14,maxAdvisorCalls:6,advisorCooldownTools:5,...config};
    for(const key of ['repeatedFailureThreshold','diagnosticAdvisorThreshold','maxAdvisorCalls','advisorCooldownTools'])
      if(!Number.isSafeInteger(this.config[key])||this.config[key]<(key==='maxAdvisorCalls'?0:1))throw new Error(`invalid ${key}`);
  }
  event(event,detail) {this.state.events.push({event,...detail});}
  cancel(reason) {
    if(this.state.pending)this.event('advisor_pending_cancelled',{trigger:this.state.pending.trigger,reason});
    this.state.pending=null;
  }
  queue(trigger,question,rows,scope) {
    if(!rows.length)return;
    const signature=digest([trigger,scope,rows.map(r=>[r.key,r.rawHashes]).filter((x,i,a)=>a.findIndex(y=>JSON.stringify(x)===JSON.stringify(y))===i)]);
    if(this.state.attempted.includes(signature)||this.state.pending?.signature===signature)return;
    if(this.state.pending&&priority[this.state.pending.trigger]>priority[trigger])return;
    this.state.pending={trigger,question,evidence_ids:rows.map(r=>r.id),scope,signature};
    this.event('advisor_queued',{trigger,evidence_ids:rows.map(r=>r.id)});
  }
  sync(scope) {
    const p=this.state.pending;
    if(p&&known(p.scope)&&known(scope)&&p.scope!==scope)this.cancel('workspace_changed_reassess_before_advice');
    if(known(scope)&&known(this.state.scope)&&scope!==this.state.scope) {
      this.state.failures=[];this.state.failureSignature=null;this.state.diagnostics=[];
    }
    this.state.scope=scope;
  }
  observe(row,readonly,localDefect) {
    this.sync(row.after);
    const s=this.state, unchanged=known(row.before)&&row.before===row.after;
    const failure=row.complete&&row.failureObserved&&unchanged&&!localDefect;
    const signature=failure?digest([row.key,row.before,row.rawHashes,row.exitCode]):null;
    s.failures=signature&&signature===s.failureSignature?[...s.failures,row].slice(-this.config.repeatedFailureThreshold):failure?[row]:[];
    s.failureSignature=signature;
    s.diagnostics=row.complete&&(row.clean||row.exitCode===null&&!row.nativeToolError)&&unchanged&&readonly?[...s.diagnostics,row].slice(-this.config.diagnosticAdvisorThreshold):[];
    if(row.complete&&row.clean&&!readonly)this.cancel('new_clean_execution_reassess_old_alarm');
    if(s.failures.length>=this.config.repeatedFailureThreshold)this.queue('repeated_failure',
      'The same command failed repeatedly with identical observed output and workspace. Suggest a different explanation and a cheap discriminating check; do not merely rename it.',s.failures,row.after);
    else if(s.diagnostics.length>=this.config.diagnosticAdvisorThreshold)this.queue('extended_diagnosis',
      'Read-only diagnosis continued without an observed workspace change. This alone does not prove stagnation. Identify the remaining unknown and a useful next check or minimal implementation.',s.diagnostics.slice(-3),row.after);
  }
  monitor(review,evidence,scope) {
    if(review.verdict==='stalled')this.queue('semantic_stall',
      `Monitor suspects stagnation (not established fact): ${review.reason}\nSuggested check: ${review.next_check}\nOffer an alternative hypothesis and a concrete distinguishing check.`,review.evidence_ids.map(id=>evidence[id]).filter(Boolean),scope);
    else if(['progress','necessary_retry'].includes(review.verdict)&&this.state.pending)this.cancel(`monitor_${review.verdict}`);
  }
  markAttempt(pending) {
    if(!pending)return;
    this.state.attempted=[...this.state.attempted,pending.signature].slice(-32);
    if(this.state.pending?.signature===pending.signature)this.state.pending=null;
  }
  drain() {return this.state.events.splice(0);}
}
