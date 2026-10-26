"""DH-native, task-local subgoals. Observed public checks, never a success oracle."""
from collections import Counter
from copy import deepcopy
import json
import re

from .lean_memory import action_key
from .lean_progress import normalize_workspace_path
from .lean_protocol import parse_action, text

SUBGOAL_INSTRUCTION = '''DH subgoals are an optional planning sidecar, not another tool or role.
On an ordinary action, define up to 4 short goals with subgoal_plan:[{
"id":"G1","title":"fix parser","acceptance":"public requirement to check",
"depends_on":[],"targets":["parser.py","test_parser.py"],
"verification":{"argv":["python","test_parser.py"],"cwd":".","stdout_contains":["parser checks passed"]}}].
IDs and definitions are stable within this task. Existing definitions cannot silently change.
Verification must test the stated requirement, NOT echo the expected marker. The controller
can check execution/output but cannot establish the semantic adequacy of a model-written test.
Use subgoal_id:"G1" on actions advancing it. Set subgoal_phase:"verify" only when running
exactly its declared verification command. A matching command already run AFTER definition
is evaluated immediately; do not repeat it merely to change its phase label.
All actual checks use the existing tool budget.
The controller alone records check_passed from complete, clean, real evidence after the
plan was declared. This means that local check passed, NOT that the task is solved.
Relevant file changes, restoring files, or invalidated prerequisites require rechecking.
subgoal_update:{"id":"G1","status":"blocked|deferred|pending","reason":"brief"}
can change focus/status without claiming success. Blocked goals remain visible.
fixed_context.subgoals suggests a ready goal; this is advice, not a command prohibition.
Do not switch away just to hide failure. Submit partial work if the budget warrants it;
unresolved goals are recorded but never prevent delivery. Invalid sidecars are ignored
with a notice, not a fatal protocol error. No extra planning/model call is required.'''


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'G[1-9][0-9]{0,2}', value):
        raise ValueError('subgoal ID must be G1..G999')
    return value


def known(value):
    return isinstance(value, str) and (value == 'missing' or value.startswith(('file:', 'dir:')))


def definition(value):
    if not isinstance(value, dict):raise ValueError('subgoal definition must be an object')
    allowed={'id','title','acceptance','depends_on','targets','verification'}
    if set(value)-allowed:raise ValueError('unsupported subgoal definition field')
    row={'id':identifier(value.get('id')), 'title':text(value.get('title'),'subgoal title',100),
         'acceptance':text(value.get('acceptance'),'acceptance criterion',240)}
    deps=value.get('depends_on',[])
    if not isinstance(deps,list) or len(deps)>4:raise ValueError('at most four prerequisites')
    row['depends_on']=list(dict.fromkeys(identifier(v) for v in deps))
    targets=value.get('targets')
    if not isinstance(targets,list) or not 1<=len(targets)<=4:raise ValueError('declare one to four relevant paths')
    row['targets']=list(dict.fromkeys(normalize_workspace_path(v) for v in targets))
    if any(len(p)>160 for p in row['targets']):raise ValueError('subgoal path too long')
    v=value.get('verification')
    if not isinstance(v,dict) or set(v)-{'argv','cwd','stdin','stdout_contains'}:
        raise ValueError('invalid verification fields')
    parse_action(dict(v,action='run'))
    command={k:deepcopy(v[k]) for k in ('argv','cwd','stdin') if k in v}
    cwd=command.get('cwd','.')
    if cwd!='.':command['cwd']=normalize_workspace_path(cwd)
    if len(json.dumps(command,ensure_ascii=False))>1000:raise ValueError('verification command must be short')
    markers=v.get('stdout_contains')
    if not isinstance(markers,list) or not 1<=len(markers)<=3:raise ValueError('declare one to three output assertions')
    row['verification']=dict(command,stdout_contains=[text(s,'output assertion',120) for s in markers])
    return row


class SubgoalLedger:
    capacity=12

    def __init__(self,emit=lambda *a,**k:None):
        self.items={};self.active=None;self.notices=[];self.stats=Counter();self.emit=emit

    def event(self,name,**fields):
        self.stats[name]+=1;self.emit('subgoal_'+name,**fields)

    def reject(self,error):
        self.notices=[str(error)[:180]]
        self.event('metadata_ignored',reason=self.notices[0],command_rejected=False)

    @staticmethod
    def validate_graph(definitions):
        done=set();visiting=set()
        def visit(key):
            if key not in definitions:raise ValueError('unknown prerequisite')
            if key in visiting:raise ValueError('cyclic subgoal dependencies')
            if key in done:return
            visiting.add(key)
            for dep in definitions[key]['depends_on']:visit(dep)
            visiting.remove(key);done.add(key)
        for key in definitions:visit(key)

    def begin(self,action):
        """Validate the whole sidecar atomically. Never reject the executable."""
        plan=action.get('subgoal_plan',[])
        if not isinstance(plan,list) or len(plan)>4:raise ValueError('subgoal_plan accepts at most four definitions')
        definitions={k:deepcopy(r['definition']) for k,r in self.items.items()};additions={}
        for raw in plan:
            row=definition(raw);key=row['id']
            if key in definitions and definitions[key]!=row:
                raise ValueError('existing goal definitions are immutable; defer it and define a new goal explicitly')
            if key not in definitions:additions[key]=row
            definitions[key]=row
        if len(definitions)>self.capacity:raise ValueError('subgoal capacity reached; no unresolved goal was evicted')
        self.validate_graph(definitions)
        update=action.get('subgoal_update')
        if update is not None:
            if not isinstance(update,dict) or set(update)!={'id','status','reason'}:raise ValueError('invalid subgoal_update')
            key=identifier(update['id'])
            if key not in definitions:raise ValueError('unknown updated goal')
            if not isinstance(update['status'],str) or update['status'] not in {'blocked','deferred','pending'}:
                raise ValueError('model cannot declare a subgoal completed or passed')
            text(update['reason'],'status reason',180)
        focus=action.get('subgoal_id',self.active)
        if focus is not None:
            identifier(focus)
            if focus not in definitions:raise ValueError('unknown focused goal')
        phase=action.get('subgoal_phase','work')
        if not isinstance(phase,str) or phase not in {'work','verify'}:raise ValueError('invalid subgoal phase')
        if phase=='verify' and (focus is None or action.get('action')!='run'):
            raise ValueError('verification requires a run action and a known goal')
        if phase=='verify' and action_key(action)!=action_key(definitions[focus]['verification']):
            raise ValueError('verification action differs from the declared check')
        self.notices=[]
        for key,row in additions.items():
            self.items[key]={'definition':row,'status':'pending','attempts':0,'checks':0,'proof':None,'last_evidence':None}
            self.event('defined',goal_id=key,definition=row)
        if update:
            r=self.items[update['id']];r['status']=update['status'];r['proof']=None
            r['reason']=update['reason'];self.event('status_changed',goal_id=update['id'],status=r['status'],reason=r['reason'])
            self.invalidate_dependents()
        if focus is not None:
            if focus!=self.active:self.event('focus_changed',previous_focus=self.active,goal_id=focus)
            self.active=focus
        if action.get('action')=='run' and focus is not None:
            if action_key(action)==action_key(definitions[focus]['verification']):phase='verify'
            return {'id':focus,'phase':phase,'command_key':action_key(action)}
        return None

    def targets(self):
        return list(dict.fromkeys(p for row in self.items.values() for p in row['definition']['targets']))

    def unmet(self,key):
        return [dep for dep in self.items[key]['definition']['depends_on'] if self.items[dep]['status']!='check_passed']

    def invalidate(self,key,reason):
        row=self.items[key];row['status']='needs_recheck';row['reason']=reason
        # Retain historical proof for the audit, never use it as current evidence.
        self.event('invalidated',goal_id=key,reason=reason)

    def invalidate_dependents(self):
        for _ in range(len(self.items)):
            changed=False
            for key,row in self.items.items():
                if row['status']=='check_passed' and self.unmet(key):
                    self.invalidate(key,'prerequisite_not_currently_checked');changed=True
            if not changed:break

    def sync(self,scope,dependencies,*,restored=False):
        for key,row in self.items.items():
            proof=row['proof']
            if row['status']!='check_passed':continue
            if restored or not proof or any(not known(v) or dependencies.get(p)!=v for p,v in proof['dependencies'].items()):
                self.invalidate(key,'workspace_restored' if restored else 'relevant_state_changed_or_unknown')
        self.invalidate_dependents()

    def observe(self,attempt,action,view,assessment):
        if not attempt or action_key(action)!=attempt['command_key']:return
        key=attempt['id'];row=self.items[key];row['attempts']+=1;row['last_evidence']=view['id']
        self.event('action_observed',goal_id=key,phase=attempt['phase'],evidence_id=view['id'])
        if attempt['phase']!='verify':return
        row['checks']+=1
        before=view.get('dependency_before',{});after=view.get('dependency_after',{})
        targets=row['definition']['targets']
        stable=all(known(after.get(p)) and before.get(p)==after.get(p) for p in targets)
        passed=(not self.unmet(key) and stable and assessment['execution_clean']
                and view['return_code']==0 and not view['timed_out'] and not view['blocked']
                and not view['capture_incomplete'] and not view['terminal_projection_incomplete']
                and all(s in view['stdout'] for s in row['definition']['verification']['stdout_contains']))
        row['status']='check_passed' if passed else 'needs_work'
        row['proof']=({'evidence_id':view['id'],'workspace':view['after'],
            'dependencies':{p:after[p] for p in targets},'command_key':attempt['command_key']} if passed else None)
        row['reason']='declared_public_check_only' if passed else 'check_failed_incomplete_changed_state_or_unmet_dependency'
        self.event('check_passed' if passed else 'check_not_passed',goal_id=key,evidence_id=view['id'],
            stable_targets=stable,unmet_dependencies=self.unmet(key),semantic_adequacy='unverified',task_success=None)
        self.invalidate_dependents()

    def view(self):
        ready=[key for key,r in self.items.items() if r['status'] not in {'check_passed','blocked','deferred'} and not self.unmet(key)]
        # Prefer prerequisites that unlock more goals; keep an eligible current focus.
        def descendants(key):
            reached={key}
            for _ in self.items:
                reached.update(k for k,r in self.items.items() if set(r['definition']['depends_on']) & reached)
            return len(reached)-1
        suggested=self.active if self.active in ready else max(ready,key=descendants,default=None)
        focus=self.active if self.active in ready or suggested is None else suggested
        rows=[dict(id=k,title=r['definition']['title'][:60],status=r['status'],depends_on=r['definition']['depends_on'],
                   attempts=r['attempts'],last_evidence=r['last_evidence']) for k,r in self.items.items()]
        current=None
        if focus in self.items:
            r=self.items[focus];current=dict(id=focus,acceptance=r['definition']['acceptance'],
                verification=r['definition']['verification'],targets=r['definition']['targets'],unmet_dependencies=self.unmet(focus))
        panel={'active':self.active,'suggested_next':suggested,'ready':ready,'goals':rows,'focus_details':current,
               'notices':self.notices,'completion_semantics':'declared local check only, never official task success'}
        # Bounded protected panel: retain every ID/status/dependency, not long labels.
        if len(json.dumps(panel,ensure_ascii=False))>3500:
            for r in rows:r.pop('title');r.pop('last_evidence');r.pop('attempts')
        if len(json.dumps(panel,ensure_ascii=False))>3500 and current:
            current.pop('verification');current['verification_ref']='immutable definition in subgoal_defined audit and prior conversation'
        # Presentation size is not a task-termination condition. The native
        # conversation budget handles projection; retain the actual goal state.
        return panel

    def snapshot(self):
        return {'active':self.active,'goals':deepcopy(self.items),'stats':dict(self.stats),
                'unresolved':[k for k,r in self.items.items() if r['status']!='check_passed'],
                'task_success':None,'semantic_adequacy_of_checks':'not_proven'}


class SubgoalHooks:
    def _init_subgoals(self):
        self.subgoals=SubgoalLedger(self._emit) if self.config.subgoals_enabled else None
        self.subgoal_attempt=None

    def _subgoal_begin(self,action):
        self.subgoal_attempt=None
        if self.subgoals is None:return
        try:self.subgoal_attempt=self.subgoals.begin(action)
        except ValueError as error:self.subgoals.reject(error)

    def _subgoal_outcome(self,action,view,assessment,*,diagnostic=False):
        if self.subgoals is None:return
        self.subgoals.sync(view['after'],view['dependency_after'])
        if not diagnostic:self.subgoals.observe(self.subgoal_attempt,action,view,assessment)
        self.subgoal_attempt=None
        self.log.save('subgoals.json',self.subgoals.snapshot())
