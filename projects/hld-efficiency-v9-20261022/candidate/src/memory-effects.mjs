import {actionKey, digest} from './policy.mjs';

// Correlation, never a causal gain claim. Bound by exact native call ID so
// concurrent observations cannot consume one another's memory-use receipts.
export class MemoryEffects {
  constructor(state) {
    this.state=state??{next:1,intervention:null,pending:{},events:[],stats:{}};
    this.state.stats={interventions:0,bound_actions:0,reviewed_actions:0,changed_actions:0,outcomes:0,workspace_changed:0,clean_checks:0,...this.state.stats};
  }
  emit(event,detail) {this.state.events.push({event,...detail,causal_benefit_proven:false});}
  intervene(call,ids,scope) {
    const signature=digest([actionKey(call),ids,scope]);
    if(this.state.intervention?.signature===signature)return;
    const row={id:`MI${this.state.next++}`,signature,memory_ids:ids,proposed_key:actionKey(call),scope};
    this.state.intervention=row;this.state.stats.interventions++;this.emit('memory_intervention',row);
  }
  bind(call,review,scope,associatedIds=[]) {
    if(!call.callId)return;
    const previous=this.state.intervention,ids=[...new Set([...(previous?.memory_ids??[]),...(Array.isArray(review?.ids)?review.ids:[]),...associatedIds])];
    if(!ids.length)return;
    const row={intervention_id:previous?.id??null,memory_ids:ids,callId:call.callId,tool:call.name,
      proposed_key:previous?.proposed_key??null,revised_key:actionKey(call),scope,
      action_changed:previous?previous.proposed_key!==actionKey(call):null,decision:review?.decision??null,
      association:review?'explicit_review':'matched_memory_without_explicit_review'};
    this.state.pending[call.callId]=row;this.state.intervention=null;
    this.state.stats.bound_actions++;if(review?.ids?.length)this.state.stats.reviewed_actions++;
    if(row.action_changed)this.state.stats.changed_actions++;
    this.emit('memory_action_bound',row);
  }
  finish(callId,row) {
    const use=this.state.pending[callId];if(!use)return;
    delete this.state.pending[callId];
    const changed=!!row?.before?.startsWith('sha256:')&&!!row?.after?.startsWith('sha256:')&&row.before!==row.after;
    this.state.stats.outcomes++;if(changed)this.state.stats.workspace_changed++;if(row?.clean)this.state.stats.clean_checks++;
    this.emit('memory_followup_outcome',{...use,evidence_id:row?.id??null,observed:!!row,complete:row?.complete??false,
      workspace_changed:changed,clean_check:row?.clean??false,exitCode:row?.exitCode??null,task_success:null});
  }
  abandonPending() {for(const id of Object.keys(this.state.pending))this.finish(id,null);}
  drain() {return this.state.events.splice(0);}
}
