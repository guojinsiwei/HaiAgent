"""Real Linux command failures + deterministic actor; no LLM/API/Docker.

This tests memory/controller plumbing, NOT autonomous model decision-making.
Repairs are deliberately scripted; all workspaces are disposable temporary copies.
"""
import copy
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_audit import read_trace, atomic_json
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import TaskSpec


def run(*argv, purpose='Fixture operation', **extra):
    return dict(action='run', argv=list(argv), cwd='.', purpose=purpose, **extra)


def scenarios():
    py = sys.executable
    bad_path = run(py,'read_value.py','missing.txt',purpose='Read requested value from missing.txt')
    missing_dep = run(py,'run.py',purpose='Run program requiring trap_dep')
    shape = run(py,'matmul.py','case.json',purpose='Validate matrix dimensions and compute product')
    base = f'{shlex.quote(py)} guard.py'
    surface = run('bash','-lc',base,purpose='Run guard check')
    variant = run('bash','-lc',f'  {shlex.quote(py)}   guard.py  ',purpose='Reformat the same guard check')
    quoted = run('bash','-lc',f"{shlex.quote(py)} 'guard.py'",purpose='Quote the same literal script argument')
    quoted_variant = run('bash','-lc',f'  {shlex.quote(py)}  "guard.py"  ',purpose='Requote the same script argument')
    verify = run(py,'verify.py','rule.py',purpose='Verify the rule on valid and invalid inputs')
    return [
        dict(name='path', label='wrong path', plan=[(bad_path,'apply'),(bad_path,'apply'),
            (bad_path,'different_route'),(run(py,'read_value.py','valid.txt',purpose='Use the existing correct path'),'different_route')],
            expected='VALUE=42', expect_refused=True),
        dict(name='dependency', label='missing dependency', plan=[(missing_dep,'apply'),(missing_dep,'apply'),
            (missing_dep,'different_route'),(run('cp','available/trap_dep.py','trap_dep.py',purpose='Add the local fixture dependency'),'different_route'),
            (missing_dep,'justified_retry')], expected='DEPENDENCY_VALUE=42', expect_refused=True),
        dict(name='shape', label='dimension mismatch', plan=[(shape,'apply'),(shape,'apply'),
            (shape,'different_route'),(run('cp','fixed.json','case.json',purpose='Replace the dimension-mismatched input'),'different_route'),
            (shape,'recheck')], expected='MATRIX_RESULT=[[22,28],[49,64]]', expect_refused=True),
        dict(name='surface', label='same failed command with whitespace changes', plan=[(surface,'apply'),(surface,'apply'),
            (variant,'different_route'),(run('cp','fixed.py','guard.py',purpose='Apply the fixture source correction'),'different_route'),
            (surface,'recheck')], expected='GUARD_FIXED=1', expect_refused=True),
        dict(name='source_change', label='same verification after a source patch', plan=[(verify,'apply'),(verify,'apply'),
            (run('cp','fixed.py','rule.py',purpose='Patch the actual rule source'),'different_route'),
            (verify,'recheck')], expected='SOURCE_CHECK=PASS', expect_refused=False),
        dict(name='surface_quotes', fixture='surface', label='failure memory across equivalent spellings',
            plan=[(surface,'apply'),(quoted,'apply'),(quoted_variant,'different_route'),
                (run('cp','fixed.py','guard.py',purpose='Apply the fixture source correction'),'different_route'),
                (surface,'recheck')], expected='GUARD_FIXED=1', expect_refused=True),
    ]


class Actor:
    def __init__(self, scenario):
        self.steps = iter(scenario['plan'])
        self.inputs, self.responses = [], []
    def complete_json(self, **kwargs):
        payload = json.loads(kwargs['user_prompt']); self.inputs.append(payload)
        action, decision = next(self.steps, (dict(action='submit',summary='Deliver fixture state; independently verify results'), 'apply'))
        action = copy.deepcopy(action)
        memories = payload['fixed_context']['memories']
        if memories:
            memory = memories[0]
            review = dict(ids=[memory['id']], observed_result=memory['conclusion'][:400],
                applicability=memory['applicability'][:300], decision=decision,
                reason='Controlled fixture decision; this is NOT an autonomous LLM decision.')
            if decision == 'justified_retry':
                review['new_evidence']='The previous fixture step added trap_dep.py; rerun import to test dependency availability.'
                action.update(uses_memory=[memory['id']], memory_reason=review['new_evidence'])
            action = dict(memory_review=review,
                strategy_adjustment='Perform the planned fixture operation and inspect its exact result against the known fixture goal.',
                **action)
        self.responses.append(action)
        return action


class NoModel:
    def complete_json(self, **kwargs):
        raise AssertionError('No monitor/advisor/model API is allowed in this fixture suite')


def execute(scenario, enabled, output):
    actor = Actor(scenario)
    with tempfile.TemporaryDirectory(prefix='bestfgs-memory-micro-') as temp:
        env = LiveWorkspace(ROOT/'microtests/fixtures'/scenario.get('fixture',scenario['name']), Path(temp)/'run')
        cfg = LeanConfig(memory_enabled=enabled, auto_memory=enabled, memory_reliability=True,
            memory_injection=True, memory_decision=True, outcome_reliability=True,
            max_turns=20,max_tools=10,wall_seconds=60,command_seconds=10,
            max_advisor_calls=0,monitor_cooldown_tools=20,monitor_interval_tools=24)
        runner = LeanTaskRunner(env,actor,NoModel(),cfg,output,monitor_client=NoModel())
        result = runner.run(TaskSpec(scenario['name'],'Resolve this isolated '+scenario['label']+' fixture and verify the result.'))
        events = read_trace(output/'events.jsonl')
        calls = [e for e in events if e['event']=='tool_call']
        successes = [e for e in calls if e['result']['return_code']==0 and scenario['expected'] in e['result']['stdout']]
        errors = [e for e in events if e['event']=='protocol_error']
        generation = [e for e in events if e['event']=='memory_admitted']
        after_fail = actor.inputs[2]['fixed_context']
        refused = any('same executable' in e['protocol_error'] for e in errors)
        changed_seen = any('changed_or_unknown_recheck_required' in m.get('applicability','')
                           for request in actor.inputs for m in request['fixed_context']['memories'])
        responses = [i for i,e in enumerate(events) if e['event']=='model_response' and e.get('role')=='action']
        third_start = responses[2]
        third_end = next((i for i in range(third_start+1,len(events))
                          if events[i]['event']=='model_request' and events[i].get('role')=='action'),len(events))
        third_executed = any(e['event']=='tool_call' for e in events[third_start:third_end])
        fixture_ok = bool(successes) and result['submitted'] and result['error_type'] is None
        behavior_ok = (fixture_ok and (not enabled or (bool(generation) and bool(after_fail['memories'])
                        and (refused if scenario['expect_refused'] else changed_seen))))
        summary = dict(case=scenario['name'], memory_enabled=enabled, controller_behavior_pass=behavior_ok,
            fixture_goal_passed=fixture_ok, automatic_memories=len(generation),
            memories_before_next_attempt=[m['id'] for m in after_fail['memories']],
            repeat_refused=refused, third_proposal_executed=third_executed,
            changed_dependency_memory_seen=changed_seen,
            failures=sum(e['result']['return_code']!=0 for e in calls),
            tools=result['tool_calls'], model_api_calls=0, logical_scripted_requests=result['interaction_rounds'],
            stop_reason=result['stop_reason'], error_type=result['error_type'],
            protocol_errors=[e['protocol_error'] for e in errors],
            trace=str(output/'events.jsonl'))
        atomic_json(output/'micro-result.json',summary)
        return summary


def main():
    if os.name!='posix': raise SystemExit('Run on Linux/WSL; production LiveWorkspace is POSIX-only')
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    output = ROOT/'evidence/microtests'
    output.mkdir(parents=True,exist_ok=False)
    results = []
    for scenario in scenarios():
        for enabled in (False,True):
            results.append(execute(scenario,enabled,output/(scenario['name']+('-memory' if enabled else '-control'))))
    tested = [r for r in results if r['memory_enabled']]
    report = dict(test_type='real Linux commands, deterministic scripted actor, no LLM/API/Docker',
        limitation='Does NOT prove autonomous model memory use. Repairs and decision summaries are scripted.',
        memory_cases_passed=sum(r['controller_behavior_pass'] for r in tested), memory_cases_total=len(tested),
        results=results)
    atomic_json(output/'summary.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
