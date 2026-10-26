"""Real model continuation after two recorded failures, paired memory on/off.

Bounded micro-CLI, NOT free-shell benchmark. The first TWO actions are controlled
failure seeds; ALL subsequent decisions come from the selected provider model.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_audit import atomic_json, read_trace
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_memory import action_key
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import CommandResult, CommandSpec, TaskSpec
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
from live_fixture_tools import CHECKS, FILES

CASES = dict(path=dict(goal='Repair missing.txt so the supplied read_value.py missing.txt check succeeds. Do not modify the checker or valid.txt.',
    protected=['read_value.py','valid.txt'],expected='VALUE=42'),
    dependency=dict(goal='Repair the missing local dependency so the supplied run.py check succeeds. Do not modify run.py or available/trap_dep.py.',
    protected=['run.py','available/trap_dep.py'],expected='DEPENDENCY_VALUE=42'),
    shape=dict(goal='Repair case.json so the supplied matmul.py case.json check computes the required product. Do not modify matmul.py or fixed.json.',
    protected=['matmul.py','fixed.json'],expected='MATRIX_RESULT=[[22,28],[49,64]]'))
CLI = '''Use ONLY the bounded microtool CLI, with argv beginning ["microtool",...].
Operations: ["microtool","list"], ["microtool","read","relative-path"],
["microtool","copy","source-path","destination-path"],
["microtool","write","relative-path","literal-file-content"], ["microtool","check"].
No shell, arbitrary interpreter code, network, or unrelated paths is supported.
Inspect the supplied files to identify a concrete correction, perform it, verify,
then submit. The same check after a real file change is a legitimate recheck.
Two controlled failed checks precede your first decision; do not invent their cause.'''


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


class NoModel:
    def complete_json(self,**kwargs):
        raise AssertionError('Auxiliary model must not run in this paired microtest')


class MicroWorkspace(LiveWorkspace):
    def __init__(self,seed,root,case):
        super().__init__(seed,root)
        self.case = case
        self.protected = {name:(self.workspace/name).read_bytes() for name in CASES[case]['protected']}
    def execute(self,action,deadline):
        argv = action['argv']
        original = CommandSpec(tuple(argv),action.get('purpose',''),action.get('cwd','.'),
            action.get('timeout_seconds',10),action.get('stdin'))
        if argv[0]!='microtool' or action.get('cwd','.')!='.' or action.get('stdin'):
            return CommandResult(original,126,'','Only bounded microtool operations in cwd . are supported',0,blocked=True)
        if any(not (self.workspace/name).is_file() or (self.workspace/name).is_symlink()
               or (self.workspace/name).read_bytes()!=content for name,content in self.protected.items()):
            return CommandResult(original,126,'','Protected fixture checker changed',0,blocked=True)
        mapped = dict(action,argv=[sys.executable,str(ROOT/'microtests/live_fixture_tools.py'),
            str(self.workspace),self.case,*argv[1:]])
        return replace(super().execute(mapped,deadline),command=original)


class LiveActor:
    def __init__(self,inner,progress):
        self.inner,self.progress = inner,progress
        self.scripted_seeds,self.provider_decisions = 0,0
        self.emit = None
    @property
    def config(self): return self.inner.config
    @property
    def last_failure_detail(self): return self.inner.last_failure_detail
    def usage_summary(self): return self.inner.usage_summary()
    def complete_json(self,**kwargs):
        if self.scripted_seeds<2:
            self.scripted_seeds += 1
            self.emit('live_test_phase',phase='scripted_failure_seed',index=self.scripted_seeds)
            return dict(action='run',argv=['microtool','check'],cwd='.',purpose='Controlled initial failed check, not a model decision')
        self.provider_decisions += 1
        self.emit('live_test_phase',phase='autonomous_provider',index=self.provider_decisions)
        self.progress(self.provider_decisions)
        return self.inner.complete_json(**kwargs)


def run_case(case,enabled,key,args,output,progress):
    cfg = RetracModelConfig(args.model,'https://api.deepseek.com',key,provider='deepseek',
        temperature=0,thinking_enabled=False,max_tokens=4096,request_attempts=2,parse_attempts=1,
        timeout_seconds=45,max_wall_time_seconds=60,retry_interval_seconds=1,stream_response=True)
    actor = LiveActor(OpenAICompatibleJSONClient(cfg),progress)
    with tempfile.TemporaryDirectory(prefix='bestfgs-live-micro-') as temp:
        env = MicroWorkspace(ROOT/'microtests/fixtures'/case,Path(temp)/'run',case)
        config = LeanConfig(memory_enabled=enabled,auto_memory=enabled,memory_decision=enabled,
            memory_reliability=True,outcome_reliability=True,memory_injection=True,
            max_turns=12,max_tools=10,wall_seconds=180,command_seconds=10,max_advisor_calls=0,
            monitor_cooldown_tools=20,monitor_interval_tools=24)
        runner = LeanTaskRunner(env,actor,NoModel(),config,output,monitor_client=NoModel())
        actor.emit = runner._emit
        task = TaskSpec(case,CASES[case]['goal']+'\n'+CLI+'\nDeclared files: '+', '.join(FILES[case]))
        result = runner.run(task)
        # Independent post-run grading uses one separate fixed checker call.
        # It is NOT an agent action and NOT part of reported agent tool counts.
        grade = env.execute(dict(action='run',argv=['microtool','check'],cwd='.',purpose='Independent fixture grader',timeout_seconds=10),time.monotonic()+12)
        verified = grade.return_code==0 and CASES[case]['expected'] in grade.stdout and not grade.output_truncated
        runner._emit('independent_fixture_grade',fixture_goal_verified=verified,
            agent_tool_call=False,return_code=grade.return_code,stdout=grade.stdout,stderr=grade.stderr)
        events = read_trace(output/'events.jsonl')
        requests = [e for e in events if e['event']=='model_request' and e['role']=='action']
        pairs, latest_request = [], None
        for event in events:
            if event['event']=='model_request' and event['role']=='action': latest_request=event
            elif event['event']=='model_response' and event['role']=='action': pairs.append((event,latest_request))
        seed_scope = next((e['after'] for e in events if e['event']=='tool_call' and e['evidence_id']=='E2'),None)
        repeats = sum(action_key(p['response'])==action_key(dict(argv=['microtool','check']))
            and q['payload']['fixed_context']['current_workspace']==seed_scope
            for p,q in pairs[2:] if isinstance(p['response'],dict))
        summary = dict(case=case,memory_enabled=enabled,scripted_failure_seeds=actor.scripted_seeds,
            provider_decisions=actor.provider_decisions,actual_api_usage=actor.usage_summary(),
            fixture_goal_verified=verified,submitted=result['submitted'],stop_reason=result['stop_reason'],
            error_type=result['error_type'],agent_tool_calls=result['tool_calls'],
            provider_requests_with_memory=sum(bool(q['memory_ids']) for q in requests[2:]),
            memory_reviews=len([e for e in events if e['event']=='memory_decision_review']),
            same_check_proposals_before_workspace_change=repeats,
            repeat_proposals_refused=sum(e['event']=='protocol_error' and 'same executable' in e['protocol_error'] for e in events),
            autonomous_repair_operations=sum(e['event']=='tool_call' and e['command']['argv'][:2] in
                (['microtool','write'],['microtool','copy']) for e in events),
            failure_tool_calls_after_seed=sum(e['event']=='tool_call' and e['evidence_id'] not in ('E1','E2')
                and e['result']['return_code']!=0 for e in events),
            trace=str(output/'events.jsonl'),causal_memory_benefit_proven=False)
        atomic_json(output/'live-result.json',runner.log.clean(summary))
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',default='deepseek-flash')
    parser.add_argument('--key-stdin',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'evidence/live-memory')
    args = parser.parse_args()
    if os.name!='posix': parser.error('Run this isolated worker on Linux')
    if not args.key_stdin: parser.error('Supply key through protected stdin; never use an argument or file')
    key = sys.stdin.readline().strip()
    if not key or len(key)>1024 or any(c.isspace() for c in key): raise ValueError('Invalid private input')
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    args.output.mkdir(parents=True,exist_ok=False)
    results = []
    started = now()
    status = dict(test_type='live provider, bounded micro-CLI, two scripted failure seeds per run',
        model=args.model,thinking=False,temperature=0,started_at=started,results=results,
        maximum_logical_provider_decisions=60,maximum_wire_attempts=120,
        limitation='Three paired toy cases, one run per arm, shared failure history. NOT a benchmark or causal effect estimate.')
    for index,case in enumerate(CASES):
        # Counterbalance arm order; no secrets or memories shared across tasks.
        for enabled in ((False,True) if index%2==0 else (True,False)):
            arm = 'memory' if enabled else 'control'
            def progress(count):
                atomic_json(args.output/'progress.json',dict(status,current_case=case,current_arm=arm,
                    provider_decisions_this_case=count,updated_at=now(),complete=False))
            progress(0)
            row = run_case(case,enabled,key,args,args.output/(case+'-'+arm),progress)
            results.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
            if row['stop_reason']=='credential_or_balance_error':
                atomic_json(args.output/'progress.json',dict(status,complete=False,requires_user_attention=True,updated_at=now()))
                return 2
    report = dict(status,complete=True,finished_at=now(),fixture_goals_verified=sum(r['fixture_goal_verified'] for r in results))
    atomic_json(args.output/'summary.json',report)
    atomic_json(args.output/'progress.json',report)
    print('LIVE_MICROTEST_COMPLETE',flush=True)
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # Never print arbitrary exception text that might contain private config.
        print('Live microtest stopped: '+type(error).__name__+'; inspect redacted run logs.',file=sys.stderr)
        raise SystemExit(2)
