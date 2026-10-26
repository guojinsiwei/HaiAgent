"""Bounded intervention -> action -> public verification, never auto execution."""
from collections import OrderedDict
import json
from .lean_audit import digest
from .lean_protocol import parse_action, text
from .lean_progress import normalize_workspace_path

CONTROL_INSTRUCTION = '''When fixed_context.recovery requests a plan, provide recovery_plan
alongside your next action. Format: {"hypothesis":"specific blocker/explanation",
"mode":"repair|diagnose", "targets":["relative/path"],
"action_argv":["program","argument"], "verification_argv":["program","argument"],
"success_contains":"specific expected output of the verification", "cwd":"."}.
Use a small executable change or discriminating check, then its separate verification.
Do not call a read-only reformulation a repair. A failed/expired plan needs a different
action or verification, not a renamed hypothesis. Only real command observations count.
Plans do not execute themselves. Public check success never establishes hidden/task success.
Use direct commands or preserve pipeline exit status. Do not swallow an exception and
claim success. Any alternative still must respect the original task constraints.
'''


def executable(action):
    cwd=action.get('cwd','.')
    if cwd=='/app':cwd='.'
    elif cwd.startswith('/app/'):cwd=cwd[5:]
    return dict(argv=action.get('argv'),cwd=cwd,stdin=action.get('stdin'))


class StagnationControl:
    def _init_control(self):
        self.recovery = None
        self.recovery_serial = 0
        self.failed_plans = []
        self.control_seen = OrderedDict()

    def control_view(self):
        if not self.config.stagnation_control or not self.recovery:
            return {}
        r=self.recovery
        return {k:r[k] for k in ('id','status','reason','created_tool','deadline_tool','plan','action_seen',
                                 'target_changed','verification_seen','last_outcome')}

    def _start_recovery(self, reason):
        if self.recovery and self.recovery['status'] not in {'failed','verified_public_check','hypothesis_checked'}:
            return
        self.recovery_serial+=1
        self.recovery=dict(id='I'+str(self.recovery_serial),status='needs_plan',reason=reason[:700],
            created_tool=self.counts['tool_calls'],deadline_tool=self.counts['tool_calls']+8,
            plan=None,action_seen=False,target_changed=False,verification_seen=False,
            last_outcome=None,gates=0,changed_dependencies={})
        self.counts['recovery_started']+=1
        self._emit('recovery_started',recovery=self.control_view())

    def control_review(self, review):
        if review['verdict']=='stalled':
            self._start_recovery(review['reason']+' Suggested check: '+review['next_check'])

    def _control_before(self, action):
        if not self.config.stagnation_control:
            return None
        r=self.recovery
        if not r or r['status'] in {'verified_public_check','hypothesis_checked'}:
            return None
        if r['status']=='failed':
            self._start_recovery('Previous plan did not resolve the blocker. Choose a different action/check. '+r['reason'])
            r=self.recovery
        proposal=action.get('recovery_plan')
        error=None
        if proposal is not None and r['plan'] is None:
            try:
                if not isinstance(proposal,dict):raise ValueError('plan must be an object')
                mode=proposal.get('mode')
                if mode not in ('repair','diagnose'):raise ValueError('invalid recovery mode')
                hypothesis=text(proposal.get('hypothesis'),'hypothesis',500)
                targets=proposal.get('targets',[])
                if not isinstance(targets,list) or len(targets)>4:raise ValueError('invalid recovery targets')
                targets=[normalize_workspace_path(p) for p in targets]
                if mode=='repair' and not targets:raise ValueError('repair requires explicit targets')
                commands=[]
                for key in ('action_argv','verification_argv'):
                    cmd=parse_action(dict(action='run',argv=proposal.get(key),cwd=proposal.get('cwd','.')))
                    if len(json.dumps(cmd))>2400:raise ValueError('recovery command too large')
                    commands.append(executable(cmd))
                expected=text(proposal.get('success_contains'),'verification success_contains',200)
                fingerprint=digest([commands,targets,mode,expected])
                if digest([fingerprint,self.environment.scope()]) in self.failed_plans:
                    raise ValueError('previously failed plan in unchanged workspace requires a different action/check')
                r['plan']=dict(hypothesis=hypothesis,mode=mode,targets=targets,action=commands[0],
                               verification=commands[1],success_contains=expected,fingerprint=fingerprint)
                r['deadline_tool']=self.counts['tool_calls']+8
                r['status']='planned'
                self.counts['recovery_plans']+=1
                self._emit('recovery_plan',intervention_id=r['id'],plan=r['plan'])
            except ValueError as exc:
                error=str(exc)
                self._emit('recovery_plan_rejected',intervention_id=r['id'],reason=error)
        # A bounded reconsideration, not an indefinite action ban. Persistent
        # noncompliance remains visible and reaches a failed episode deadline.
        if r['plan'] is None and action['action']=='run' and r['gates']<2:
            r['gates']+=1
            return dict(recovery_id=r['id'],not_executed=True,
                        instruction=error or 'Provide a concrete recovery_plan: hypothesis, action, targets and verifiable expected outcome.')
        return None

    def _control_outcome(self, action, row, assessment):
        if not self.config.stagnation_control:
            return
        key=digest([executable(action),row['before'],row['after'],row.get('outcome_key')])
        self.control_seen[key]=self.control_seen.get(key,0)+1
        self.control_seen.move_to_end(key)
        while len(self.control_seen)>96:self.control_seen.popitem(last=False)
        if self.control_seen[key]>=3:
            self.monitor_event='repeated_observation'
            self._start_recovery('The same command, observable state and output recurred at least three times. '
                                 'Explain a legitimate retry or select a discriminating action; repetition alone is not failure proof.')
        r=self.recovery
        if not r or r['status'] in {'failed','verified_public_check','hypothesis_checked'}:return
        p=r['plan']; command=executable(action)
        r['last_outcome']=dict(evidence_id=row['id'],execution_clean=assessment['execution_clean'],
                               check_status=assessment['check_status'],signals=assessment['signals'])
        changed={t:row.get('dependency_after',{}).get(t) for t in (p or {}).get('targets',[])
                 if row.get('dependency_before',{}).get(t) is not None
                 and row.get('dependency_after',{}).get(t) not in (None,'unknown')
                 and row['dependency_before'][t]!=row['dependency_after'][t]}
        was_action_seen=r['action_seen']
        if p and command==p['action']:
            r['action_seen']=True;r['status']='awaiting_verification'
            r['target_changed']=r['target_changed'] or bool(changed)
            r['changed_dependencies'].update(changed)
        if p and was_action_seen and command==p['verification']:
            r['verification_seen']=True
            stable=all(row.get('dependency_after',{}).get(t)==v for t,v in r['changed_dependencies'].items())
            verified=(assessment['execution_clean'] and not row['capture_incomplete']
                      and p['success_contains'] in row['stdout']+'\n'+row['stderr'])
            if verified and (p['mode']=='diagnose' or r['target_changed'] and stable):
                r['status']='verified_public_check' if p['mode']=='repair' else 'hypothesis_checked'
                self.counts['recovery_verified_repairs' if p['mode']=='repair' else 'recovery_checked_hypotheses']+=1
            else:
                self._fail_recovery('verification_failed_or_no_matching_target_change')
        if r['status'] not in {'failed','verified_public_check','hypothesis_checked'} and self.counts['tool_calls']>=r['deadline_tool']:
            self._fail_recovery('plan_not_completed_within_eight_tools')
        self._emit('recovery_followup',recovery=self.control_view(),task_success=None,causal_benefit_proven=False)

    def _fail_recovery(self, reason):
        r=self.recovery;r['status']='failed'
        if r['plan']:self.failed_plans=(self.failed_plans+[digest([r['plan']['fingerprint'],self.environment.scope()])])[-12:]
        self.counts['recovery_failed']+=1
        self.monitor_event='recovery_failed'
        self.pending_question='Recovery failed: '+reason+'. Choose a genuinely different hypothesis/action/check, not another reading of the same evidence.'
        self.pending_question_trigger='recovery_failed'
        self._emit('recovery_failed',intervention_id=r['id'],reason=reason)
