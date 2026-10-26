"""Task-local error routes with shared budgets and observed public verification."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
import re
import shlex

from .lean_runtime import LeanTaskRunner
from .lean_protocol import parse_action
from .lean_memory import action_key
from .models import ModelCallError


@dataclass(frozen=True)
class RoutingPolicy:
    local_correction: bool = True
    reconnaissance: bool = True
    critic: bool = False
    backtracking: bool = False
    correction_limit: int = 3
    critic_limit: int = 2
    critic_checks: int = 2
    rollback_limit: int = 2

    def __post_init__(self):
        if self.backtracking and not self.critic:
            raise ValueError('backtracking arm requires critic')
        if any(type(getattr(self, k)) is not bool for k in
               ('local_correction','reconnaissance','critic','backtracking')):
            raise ValueError('route switches must be boolean')
        if any(type(getattr(self, k)) is not int or getattr(self, k)<1 for k in
               ('correction_limit','critic_limit','critic_checks','rollback_limit')):
            raise ValueError('route limits must be positive integers')


ROUTING_INSTRUCTION = '''Use the task-local error_routes panel when present.
Define a small subgoal_plan covering the public task requirements as you inspect
INSTRUCTION.md. Keep unmet requirements visible, and use substantive verification.
local_correction: when an unexecuted protocol/parameter error or observed syntax/
usage error is displayed, retain the current requirement and fix that specific
format/argument/syntax defect. Orthogonality is suspended for a bounded correction;
unchanged failed actions are still subject to the final duplicate guard.
reconnaissance: simple approved read/search/list commands may gather missing facts
without three-dimensional orthogonality. Shell composites and arbitrary scripts
have no such exemption. Use cached evidence rather than rereading unchanged data.
Completion checks and rollback are task-local and spend the same total budgets.
Do not equate a public check or critic acceptance with official benchmark success.'''

CRITIC_SYSTEM = '''You independently review a CLI artifact against the ORIGINAL
public task. Actor claims and local check_passed labels are fallible. Inspect the
supplied requirements, public evidence, changes, and unresolved subgoals. Identify
requirements omitted by the actor. Never inspect hidden tests, reference answers,
grader files or official scores. Return one compact JSON object:
{"decision":"accept|revise","requirements":["public requirement checked"],
 "gaps":["specific missing implementation or coverage"],"checks":[
 {"argv":["program","argument"],"cwd":".","stdout_contains":[]}]}
Propose one or two meaningful bounded public checks on the actual artifact.
Use the project's public build/tests or assertions derived from public requirements.
Never true/echo success, cosmetic file existence alone, or weakening a failed test.
The harness executes checks and decides whether their real receipts are clean.
In stage=verdict, inspect the supplied real check observations and return the SAME
schema with checks:[]; no further commands are requested in that stage.
No completion from prose. If evidence is insufficient, state the gap. This review
cannot establish official success or prove that model-written checks are adequate.'''


def readonly_action(action):
    """Conservative lexical admission; never execute/rewrite a proposed command."""
    argv=action.get('argv',[])
    if not argv or action.get('stdin') is not None:return False
    if argv[0] in ('sh','bash') and len(argv)==3 and argv[1] in ('-c','-lc'):
        script=argv[2]
        if any(c in script for c in '$`\n\r') or re.search(r'[;&|<>]',script):return False
        try:argv=shlex.split(script)
        except ValueError:return False
    if not argv:return False
    # Only sandbox-installed utility names, not a same-named workspace executable.
    program=argv[0]
    if '/' in program and not program.startswith(('/bin/','/usr/bin/')):return False
    name=program.rsplit('/',1)[-1]
    if any('\x00' in a for a in argv):return False
    if name in {'pwd','ls','cat','head','tail','wc','stat','file','grep','rg','diff'}:
        # Reject shell-style execution hooks even when a utility supports them.
        return not any(a.startswith(('--pre','--pre-glob','--files-with-matches=')) for a in argv[1:])
    return False


def execution_defect(row):
    if row.get('return_code')==0 or row.get('timed_out') or row.get('blocked'):return None
    text=(row.get('stderr','')+'\n'+row.get('stdout',''))[:12000]
    patterns=[('syntax',r'\b(?:SyntaxError|IndentationError|TabError)\b|syntax error near'),
              ('argument',r'unrecognized arguments|invalid option|unknown option|missing required argument')]
    for kind,pattern in patterns:
        if re.search(pattern,text,re.I):return kind
    return None


class RoutedTaskRunner(LeanTaskRunner):
    def __init__(self,*args,routing=None,critic_client=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.routing=routing or RoutingPolicy()
        if self.routing.critic:
            if critic_client is None:raise ValueError('critic client required')
            transport=getattr(critic_client,'inner',critic_client)
            if any(transport is getattr(c,'inner',c) for c in self.clients.values()):
                raise ValueError('critic requires an independent client instance')
            self.clients['critic']=critic_client
        self.route_stats=Counter();self.local=None;self.healthy=[];self.pending_rollback=None
        self.regressions=Counter();self.critic_rounds=0;self.critic_decision='disabled'
        self.critic_receipts=[];self.route_bypass=None;self.critic_cache={}

    def _emit(self,event,**fields):
        if event=='header':fields['routing_policy']=self.routing.__dict__
        return super()._emit(event,**fields)

    def _role_system(self,role):
        if role=='critic':return CRITIC_SYSTEM
        value=super()._role_system(role)
        if role=='action':value+='\n'+ROUTING_INSTRUCTION
        return value

    def _panel(self,*args,**kwargs):
        panel=super()._panel(*args,**kwargs)
        panel['error_routes']={'local_correction':deepcopy(self.local),
            'reconnaissance_exemption':self.routing.reconnaissance,
            'critic_enabled':self.routing.critic,'critic_rounds':self.critic_rounds,
            'backtracking_enabled':self.routing.backtracking,
            'healthy_checkpoints':[{'id':x['checkpoint'],'goals':x['goals']} for x in self.healthy
                if x['checkpoint'] in self.checkpoints],
            'budgets':'all auxiliary requests and commands count toward original totals'}
        return panel

    def _set_local(self,kind,reason,action=None):
        if not self.routing.local_correction:return
        self.local={'kind':kind,'error':str(reason)[:600],'remaining':self.routing.correction_limit,
                    'goal_id':(action or {}).get('subgoal_id'),
                    'instruction':'Keep the current requirement; correct only the reported defect.'}
        self.route_stats['local_episodes']+=1
        self._emit('error_route',route='local_correction',kind=kind,remaining=self.local['remaining'])

    def _protocol_feedback(self,raw,error):
        self._set_local('protocol',error,raw if isinstance(raw,dict) else None)
        self.last_feedback.update(error_route='local_correction',
            instruction='No command executed. Retain the current requirement; repair the reported field or format.')

    def _ask(self,role,*args,**kwargs):
        if role=='action' and self.pending_rollback:self._apply_rollback()
        try:return super()._ask(role,*args,**kwargs)
        except ModelCallError:
            detail=getattr(self.clients.get(role),'last_failure_detail',None)
            if role=='action' and detail in {'json_syntax','json_root_type','schema_validation','output_length','empty_content'}:
                self._set_local('model_format',detail)
            raise

    def _contrastive_before(self,action):
        self.route_bypass=None
        if action.get('action')=='run':
            if self.local and self.local['remaining']>0:
                self.local['remaining']-=1;self.route_bypass='local_correction'
            elif self.routing.reconnaissance and readonly_action(action):
                self.route_bypass='reconnaissance'
            if self.route_bypass:
                self.contrastive_pending=None
                self.route_stats[self.route_bypass+'_admissions']+=1
                self._emit('error_route_admission',route=self.route_bypass,
                    command_key=action_key(action),duplicate_guard_retained=True)
                return None
        return super()._contrastive_before(action)

    def _contrastive_instruction(self):
        return super()._contrastive_instruction()+('\nError routing takes precedence for a bounded local '
            'format/syntax correction or an approved simple read utility. These actions do not need '
            'contrastive proof. The final unchanged-action guard remains active.')

    def _contrastive_outcome(self,action,row,assessment):
        defect=execution_defect(row)
        if defect and self.routing.local_correction:
            if not self.local:
                self._set_local(defect,(row.get('stderr','')+'\n'+row.get('stdout',''))[:600],action)
            elif self.local['remaining']<=0:
                self.local=None
                return super()._contrastive_outcome(action,row,assessment)
            self.contrastive_pending=None
            self.route_stats['execution_defects']+=1
            self._emit('error_route_execution_defect',evidence_id=row['id'],kind=defect,
                       strategy_failure_recorded=False)
            return
        if self.local:
            self.local=None
            self._emit('error_route_local_end',evidence_id=row['id'],execution_clean=assessment['execution_clean'])
        return super()._contrastive_outcome(action,row,assessment)

    def _subgoal_outcome(self,action,view,assessment,*,diagnostic=False):
        old={k:r['status'] for k,r in self.subgoals.items.items()} if self.subgoals else {}
        attempt=deepcopy(self.subgoal_attempt)
        super()._subgoal_outcome(action,view,assessment,diagnostic=diagnostic)
        if not self.routing.backtracking or diagnostic or not self.subgoals:return
        passed=[k for k,r in self.subgoals.items.items() if r['status']=='check_passed']
        new=[k for k in passed if old.get(k)!='check_passed']
        if new and self.counts['checkpoints_created']<self.config.max_checkpoints-1:
            checkpoint=self._checkpoint('verified subgoal '+','.join(new),'Actual declared public checks passed')
            self.healthy.append({'checkpoint':checkpoint,'goals':passed,
                'scope':view['after'],'definitions':{k:deepcopy(self.subgoals.items[k]['definition']) for k in passed}})
            self.healthy=[x for x in self.healthy if x['checkpoint'] in self.checkpoints]
            self.route_stats['healthy_snapshots']+=1
        if attempt and attempt['phase']=='verify':
            key=attempt['id'];row=self.subgoals.items[key]
            candidates=[x for x in self.healthy if key in x['goals']
                and x['checkpoint'] in self.checkpoints and x['scope']!=view['after']
                and x['definitions'][key]==row['definition']]
            # A previously verified fixed check must fail twice on changed task state.
            # Neither novelty rejections nor failure on a new requirement proves regression.
            complete=not any(view.get(k) for k in ('timed_out','blocked','capture_incomplete','terminal_projection_incomplete'))
            if candidates and row['status']!='check_passed' and complete and view['return_code']!=0:
                self.regressions[key]+=1
                if self.regressions[key]>=2 and self.route_stats['rollbacks']<self.routing.rollback_limit:
                    self.pending_rollback=candidates[-1]
                    self._emit('rollback_requested',goal_id=key,evidence_id=view['id'],
                               checkpoint_id=candidates[-1]['checkpoint'],reason='fixed_check_regressed_twice')
            elif row['status']=='check_passed':self.regressions[key]=0

    def _apply_rollback(self):
        item=self.pending_rollback;self.pending_rollback=None
        target=self.checkpoints.get(item['checkpoint'])
        if not target:return
        if self.counts['checkpoints_created']>=self.config.max_checkpoints:
            self._emit('rollback_deferred',reason='no_capacity_to_preserve_current_files');return
        source=self._checkpoint('before automatic rollback','Preserve all current task files',pin=target['id'])
        self.environment.restore(target['record'])
        self.subgoals.sync(self.environment.scope(),{},restored=True)
        self.anchor=target['id'];self.counts['branch_restores']+=1;self.route_stats['rollbacks']+=1
        edge={'source':source,'target':target['id'],'reason':'observed regression of a fixed subgoal check'}
        self.edges.append(edge);self.contrastive_episode=None;self.contrastive_pending=None
        self.failure_streak=0;self.failure_signature=None;self.regressions.clear();self.local=None
        self.last_feedback={'restored':target['id'],'preserved_attempt':source,
            'instruction':'Recheck restored files. Old passed statuses are invalid; choose a different repair.'}
        self._emit('automatic_rollback',**edge,completion_statuses_invalidated=True)
        self.log.save('graph.json',{'nodes':self.graph,'edges':self.edges,'current':self.anchor})

    def _before_submit(self,action):
        if not self.routing.critic:return None
        if self.critic_rounds>=self.routing.critic_limit:
            self.critic_decision='partial_delivery_review_limit'
            self._emit('critic_partial_delivery',reason='review_limit',official_success=None)
            return None
        self.critic_rounds+=1
        payload=self._panel('Independently check coverage and actual artifacts')
        payload.update(stage='plan_checks',original_task=self.task.goal,actor_summary=action['summary'],
                       max_checks=self.routing.critic_checks,
                       instruction='Provide public requirement coverage, concrete gaps, and meaningful checks.')
        try:
            response=self._ask('critic',payload_override=payload)
            if not isinstance(response,dict) or set(response)!={'decision','requirements','gaps','checks'}:
                raise ValueError('invalid critic object')
            if response['decision'] not in {'accept','revise'}:raise ValueError('invalid critic decision')
            for field in ('requirements','gaps'):
                if not isinstance(response[field],list) or len(response[field])>12 or any(
                    not isinstance(v,str) or not v.strip() or len(v)>600 for v in response[field]):
                    raise ValueError('invalid critic '+field)
            checks=response['checks']
            if not isinstance(checks,list) or not 1<=len(checks)<=self.routing.critic_checks:
                raise ValueError('critic must propose bounded real checks')
            parsed=[]
            for check in checks:
                if not isinstance(check,dict) or set(check)-{'argv','cwd','stdout_contains','timeout_seconds'}:
                    raise ValueError('invalid critic check')
                markers=check.get('stdout_contains',[])
                if not isinstance(markers,list) or any(not isinstance(s,str) or len(s)>300 for s in markers):
                    raise ValueError('invalid critic markers')
                cmd=parse_action(dict(action='run',**{k:v for k,v in check.items() if k!='stdout_contains'}))
                if cmd['argv'][0] in {'true','echo',':'}:raise ValueError('trivial critic check')
                parsed.append((cmd,markers))
            receipts=[];observations=[]
            for cmd,markers in parsed:
                cache_key=(action_key(cmd),self.environment.scope())
                row=self.critic_cache.get(cache_key)
                reused=row is not None
                feedback={}
                if row is None:
                    feedback=self._run_command(cmd,diagnostic=True)
                    row=self.last_tool_observation.get('evidence',{}) if not feedback.get('not_executed') else {}
                    if row and row['before']==row['after']:
                        self.critic_cache[(action_key(cmd),row['after'])]=deepcopy(row)
                clean=bool(row and row.get('return_code')==0 and not any(row.get(k) for k in
                    ('timed_out','blocked','capture_incomplete','terminal_projection_incomplete'))
                    and row.get('execution_assessment',{}).get('execution_clean')
                    and all(s in row.get('stdout','') for s in markers))
                receipts.append({'evidence_id':row.get('id'),'passed':clean,
                    'not_executed':bool(feedback.get('not_executed')),'command_key':action_key(cmd),
                    'reused_current_receipt':reused})
                observations.append({'command':cmd,'receipt':receipts[-1],
                    'stdout':row.get('stdout','')[:10000],'stderr':row.get('stderr','')[:6000],
                    'exit_code':row.get('return_code'),'workspace_changed':row.get('before')!=row.get('after')})
            final_payload=self._panel('Decide after inspecting the actual public check observations')
            final_payload.update(stage='verdict',original_task=self.task.goal,actor_summary=action['summary'],
                proposed_review=response,actual_check_observations=observations,
                instruction='Return the same schema with checks:[]; decide coverage from actual observations.')
            verdict=self._ask('critic',payload_override=final_payload)
            if not isinstance(verdict,dict) or set(verdict)!={'decision','requirements','gaps','checks'}:
                raise ValueError('invalid critic verdict')
            if verdict['decision'] not in {'accept','revise'} or verdict['checks']!=[]:
                raise ValueError('invalid bounded critic verdict')
            for field in ('requirements','gaps'):
                if not isinstance(verdict[field],list) or len(verdict[field])>12 or any(
                    not isinstance(v,str) or not v.strip() or len(v)>600 for v in verdict[field]):
                    raise ValueError('invalid critic verdict '+field)
            accepted=(verdict['decision']=='accept' and not verdict['gaps'] and bool(verdict['requirements'])
                      and all(r['passed'] for r in receipts) and any(not readonly_action(cmd) for cmd,_ in parsed))
            self.critic_receipts.extend(receipts);self.route_stats['critic_reviews']+=1
            self.critic_decision='public_review_accepted' if accepted else 'needs_revision'
            self._emit('critic_review',response=response,verdict=verdict,receipts=receipts,accepted=accepted,
                       official_success=None,semantic_coverage_proven=False)
            if accepted:return None
            return {'submission_deferred':True,'critic_gaps':verdict['gaps'],
                    'critic_checks':receipts,'instruction':'Repair concrete gaps using actual evidence; partial delivery remains possible after bounded review.'}
        except (ValueError,ModelCallError) as error:
            self.critic_decision='review_unavailable'
            self._emit('critic_review_unavailable',error_type=type(error).__name__,official_success=None)
            return {'submission_deferred':True,'critic_error':type(error).__name__,
                    'instruction':'Review unavailable; preserve work and continue or request bounded partial delivery.'}

    def run(self,task):
        result=super().run(task)
        result['version']='DH-routing-v1'
        result['routing']={'policy':self.routing.__dict__,'stats':dict(self.route_stats),
                           'critic_decision':self.critic_decision,'critic_receipts':self.critic_receipts,
                           'official_success':None}
        self.log.save('routing.json',result['routing']);self.log.save('result.json',result)
        return result
