"""KZDSH goal revision and receipt binding on the native KZ sidecar."""
from copy import deepcopy
from native_repair import RepairLedger
from bestfgs.subgoals import definition, identifier
from bestfgs.lean_memory import action_key
from bestfgs.verification_identity import verification_key


class AlignedLedger(RepairLedger):
    def check_identity(self,action):
        return verification_key(action,self.workspace.as_posix())

    def begin(self,action):
        value=self.normalize(action);warnings=[]
        plan=value.get('subgoal_plan',[])
        if not isinstance(plan,list) or len(plan)>4:raise ValueError('subgoal_plan accepts up to four definitions')
        for raw in plan:
            try:row=definition(raw)
            except ValueError as error:
                try:row=definition(dict(raw,verification=None));warnings.append(str(error))
                except (ValueError,TypeError):
                    self.rejected_plan=deepcopy(plan);self.plan_error=str(error);warnings.append(str(error));continue
            key=row['id'];old=self.items.get(key)
            if old and old['definition']!=row:
                warnings.append('Use explicit subgoal_update with reason for '+key);continue
            if not old:
                if len(self.items)>=self.capacity:warnings.append('Subgoal capacity reached');continue
                self.items[key]=dict(definition=row,revision=1,history=[],status='pending',attempts=0,checks=0,proof=None,last_evidence=None)
                self.event('defined',goal_id=key,definition=row)
        update=value.get('subgoal_update')
        if update is not None:
            try:
                if not isinstance(update,dict) or not isinstance(update.get('reason'),str) or not update['reason'].strip():raise ValueError('Explicit update needs reason')
                item=self.items.get(update.get('id'))
                if item is None:raise ValueError('Unknown updated goal')
                if update.get('expected_revision',item['revision'])!=item['revision']:raise ValueError('Stale subgoal revision')
                if update.get('status','pending') not in ('pending','blocked','deferred'):raise ValueError('Model cannot declare a passing goal')
                patch={k:deepcopy(update[k]) for k in ('title','acceptance','depends_on','targets','verification') if k in update}
                if not patch and 'status' not in update:raise ValueError('Update needs a definition or status change')
                raw=dict(item['definition'],**patch)
                # Normalize absolute native paths in updated definitions too.
                raw=self.normalize({'subgoal_plan':[raw]})['subgoal_plan'][0]
                try:row=definition(raw)
                except ValueError as error:
                    if 'verification' not in patch:raise
                    row=definition(dict(raw,verification=None));warnings.append(str(error))
                if row!=item['definition']:
                    item['history'].append(dict(revision=item['revision'],definition=deepcopy(item['definition']),proof=deepcopy(item['proof']),reason=update['reason']))
                    item['revision']+=1;item['definition']=row
                item['status']=update.get('status','pending');item['proof']=None
                self.event('definition_updated',goal_id=update['id'],revision=item['revision'])
            except (ValueError,TypeError) as error:warnings.append(str(error))
        def problem(key,stack=()):
            if key not in self.items:return 'missing prerequisite'
            if key in stack:return 'dependency cycle'
            for dep in self.items[key]['definition']['depends_on']:
                issue=problem(dep,stack+(key,))
                if issue:return issue
            return None
        for key,item in self.items.items():
            item['dependency_problem']=problem(key)
            if item['dependency_problem'] and item['status']=='check_passed':self.invalidate(key,'invalid_dependency_graph')
        focus=value.get('subgoal_id',self.active)
        if focus in self.items:self.active=focus
        elif focus is not None:warnings.append('Unknown focused goal '+str(focus))
        self.notices=warnings;self.invalidate_dependents();self.advance()
        if not warnings and plan:self.rejected_plan=None;self.plan_error=None
        if value.get('action')=='run' and self.active in self.items:
            verification=self.items[self.active]['definition']['verification']
            phase='verify' if verification and self.check_identity(action)==self.check_identity(verification) else 'work'
            return dict(id=self.active,phase=phase,command_key=action_key(action))

    def unmet(self,key):
        return [dep for dep in self.items[key]['definition']['depends_on'] if self.items.get(dep,{}).get('status')!='check_passed']

    def advance(self):
        ready=[k for k,r in self.items.items() if r['status'] not in ('check_passed','blocked','deferred') and not r.get('dependency_problem') and not self.unmet(k)]
        if self.active not in ready:self.active=ready[0] if ready else self.active

    def observe(self,attempt,action,view,assessment):
        # Every actual matching check can prove its goal; focus metadata is optional.
        for key,item in self.items.items():
            verification=item['definition']['verification']
            if item['status'] in ('blocked','deferred') or not verification or item.get('dependency_problem'):continue
            if self.check_identity(action)!=self.check_identity(verification):continue
            previous=item.get('proof')
            if previous and previous.get('evidence_id')==view['id']:continue
            super().observe(dict(id=key,phase='verify',command_key=action_key(action)),action,view,assessment)
            if item['proof']:item['proof']['revision']=item['revision']
        self.advance()

    def bind(self,goal_id,evidence_id,evidence,current_dependencies):
        item=self.items.get(goal_id);row=evidence.get(evidence_id)
        if not item or not row or not row.get('command'):raise ValueError('Binding needs a known goal and actual command receipt')
        verification=item['definition']['verification']
        if not verification or self.check_identity(row['command'])!=self.check_identity(verification):raise ValueError('Receipt does not match verification')
        if any(current_dependencies.get(p)!=row.get('dependency_after',{}).get(p) for p in item['definition']['targets']):raise ValueError('Receipt targets have changed')
        newer=[r for r in evidence.values() if r.get('command') and self.check_identity(r['command'])==self.check_identity(row['command']) and int(r['id'][1:])>int(evidence_id[1:])]
        if newer:raise ValueError('Newer verification supersedes this receipt')
        self.observe(None,row['command'],row,row.get('execution_assessment',{}))
