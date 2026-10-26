"""Small paired mechanism test, NOT a benchmark or a trained contrastive learner.

Two controlled failed commands precede autonomous real provider decisions.
Both arms use identical memory generation, fixtures, model and hard budgets.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'sources/bestfgs-project/src'))
from bestfgs.lean_audit import atomic_json, read_trace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
from run_live_memory import CASES, CLI, MicroWorkspace, NoModel, LiveActor, now
from live_fixture_tools import FILES

CASES['parameter'] = dict(goal='Generate report.json with a valid threshold and loss using microtool evaluate --threshold VALUE. Follow spec.json. Do not modify spec.json or validate_parameter.py.',
    protected=['spec.json', 'validate_parameter.py'], expected='PARAMETER_REPORT_VALID')
CASE_ORDER = ['path', 'parameter', 'dependency', 'shape']
ARMS = ['evidence', 'orthogonal']
BUDGETS = dict(max_turns=16, max_tools=12, wall_seconds=240, command_seconds=10,
               max_advisor_calls=0, max_consecutive_errors=3, contrastive_episode_tools=8)


class ContrastWorkspace(MicroWorkspace):
    def contrastive_dependencies(self, action):
        # Public declared inputs of the immutable tool, NOT checker outcomes.
        # Supplying this manifest is identical in both arms.
        if action['argv'][:2] == ['microtool','check']:
            return dict(path=['read_value.py','missing.txt'], dependency=['run.py','trap_dep.py'],
                shape=['matmul.py','case.json'], parameter=['validate_parameter.py','report.json'])[self.case]
        if len(action['argv']) > 2 and action['argv'][1] in {'read','write','copy'}:
            return [v for v in action['argv'][2:] if v in FILES[self.case]]
        return []


class ContrastActor(LiveActor):
    def __init__(self, inner, progress, case):
        super().__init__(inner, progress)
        self.case = case
    def complete_json(self, **kwargs):
        if self.scripted_seeds < 2 and self.case == 'parameter':
            self.scripted_seeds += 1
            self.emit('live_test_phase', phase='scripted_failure_seed', index=self.scripted_seeds)
            return dict(action='run', argv=['microtool','evaluate','--threshold','2'], cwd='.',
                        purpose='Controlled initial invalid parameter, not a model decision')
        return super().complete_json(**kwargs)


def run_pair_member(case, arm, key, args, output, progress, transport_factory=None):
    cfg = RetracModelConfig(args.model, 'https://api.deepseek.com', key, provider='deepseek',
        temperature=0, thinking_enabled=False, max_tokens=4096, request_attempts=2, parse_attempts=1,
        timeout_seconds=45, max_wall_time_seconds=60, retry_interval_seconds=1, stream_response=True)
    actor = ContrastActor((transport_factory or OpenAICompatibleJSONClient)(cfg), progress, case)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='contrastive-pair-') as temp:
        env = ContrastWorkspace(ROOT/'microtests/fixtures'/case, Path(temp)/'run', case)
        config = LeanConfig(contrastive_mode=arm, contrastive_threshold=.8, memory_enabled=True,
            auto_memory=True, memory_decision=True, memory_reliability=True, outcome_reliability=True,
            memory_injection=True, monitor_cooldown_tools=20, monitor_interval_tools=24, **BUDGETS)
        runner = LeanTaskRunner(env, actor, NoModel(), config, output, monitor_client=NoModel())
        actor.emit = runner._emit
        extra = ('\nAdditional allowed operation: ["microtool","evaluate","--threshold","VALUE"]. '
                 'It writes report.json only when the supplied numeric parameter is valid. '
                 'report.json cannot be written or copied directly.' if case == 'parameter' else '')
        task = TaskSpec(case, CASES[case]['goal']+'\n'+CLI+extra+'\nDeclared files: '+', '.join(FILES[case]))
        result = runner.run(task)
        grade = env.execute(dict(action='run', argv=['microtool','check'], cwd='.',
            purpose='Independent post-run fixture grader', timeout_seconds=10), time.monotonic()+12)
        verified = grade.return_code == 0 and CASES[case]['expected'] in grade.stdout and not grade.output_truncated
        runner._emit('independent_fixture_grade', fixture_goal_verified=verified, agent_tool_call=False,
                    return_code=grade.return_code, stdout=grade.stdout, stderr=grade.stderr)
        traces = read_trace(output/'events.jsonl')
        calls = [e for e in traces if e['event'] == 'tool_call']
        autonomous = calls[2:]
        gates = [e for e in traces if e['event'] == 'contrastive_validation']
        observed_checks = [e for e in autonomous if e['command']['argv'] == ['microtool','check']]
        wire = [e for e in traces if e['event'] == 'wire_prompt']
        usage = actor.usage_summary()
        summary = dict(case=case, arm=arm, model=args.model, thinking=False, temperature=0,
            scripted_failure_seeds=actor.scripted_seeds, provider_decisions=actor.provider_decisions,
            actual_api_usage=usage, wire_attempts=len(wire), fixture_goal_verified=verified,
            submitted=result['submitted'], verified_and_submitted=verified and result['submitted'],
            stop_reason=result['stop_reason'], error_type=result['error_type'], agent_tool_calls=result['tool_calls'],
            autonomous_tool_calls=len(autonomous), elapsed_seconds=time.monotonic()-started,
            autonomous_failed_calls=sum(e['result']['return_code'] != 0 for e in autonomous),
            public_verification_passed_by_actor=any(e['result']['return_code'] == 0 for e in observed_checks),
            contrastive_proposals=len(gates), contrastive_rejections=sum(not e['accepted'] for e in gates),
            contrastive_outcomes=sum(e['event'] == 'contrastive_outcome' for e in traces),
            gate_reasons=[e['reason'] for e in gates if not e['accepted']],
            executed_actions=[dict(evidence_id=e['evidence_id'], argv=e['command']['argv'],
                                   return_code=e['result']['return_code']) for e in autonomous],
            candidate_predictions_are_not_causal_proof=True, task_success_is_independently_graded=True)
        atomic_json(output/'contrastive-result.json', runner.log.clean(summary))
        return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--key-stdin', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'evidence/live-contrastive')
    args = parser.parse_args()
    if os.name != 'posix' or not args.key_stdin:
        parser.error('Run on isolated Linux with protected --key-stdin')
    key = sys.stdin.readline().strip()
    if not key or len(key) > 1024 or any(c.isspace() for c in key):
        raise ValueError('Invalid protected key input')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    metadata = dict(test_type='four paired bounded CLI fixtures, two scripted failures each',
        model=args.model, thinking=False, temperature=0, started_at=now(), budgets=BUDGETS,
        threshold=.8, case_order=CASE_ORDER, results=results,
        maximum_provider_decisions=112, maximum_wire_attempts=224,
        limitations=['One repetition per fixture/arm; diagnostic pilot, not benchmark evidence.',
            'Initial failures are controlled seeds; no claim that the model discovered them.',
            'Shared v8 memory review/gate retained; this tests the added exploration policies.',
            'TF-IDF uses exact default sklearn word weighting; no training objective/weights updated.',
            'No HAI route search, branches, rollbacks, macros or extra judge model.',
            'Post-run grading is separate and cannot guide the solver.'])
    for index, case in enumerate(CASE_ORDER):
        for arm in ARMS if index % 2 == 0 else list(reversed(ARMS)):
            def progress(count):
                atomic_json(args.output/'progress.json', dict(metadata, current_case=case, current_arm=arm,
                    current_provider_decisions=count, updated_at=now(), complete=False))
            progress(0)
            row = run_pair_member(case, arm, key, args, args.output/(case+'-'+arm), progress)
            results.append(row)
            print(json.dumps({k: row[k] for k in ('case','arm','fixture_goal_verified','submitted',
                'agent_tool_calls','provider_decisions','contrastive_rejections','stop_reason')}, ensure_ascii=False), flush=True)
            if row['stop_reason'] == 'credential_or_balance_error':
                atomic_json(args.output/'progress.json', dict(metadata, complete=False, requires_user_attention=True))
                return 2
    report = dict(metadata, finished_at=now(), complete=True)
    atomic_json(args.output/'summary.json', report)
    atomic_json(args.output/'progress.json', report)
    print('CONTRASTIVE_PILOT_COMPLETE', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print('Contrastive pilot stopped: '+type(error).__name__+'; inspect redacted logs.', file=sys.stderr)
        raise SystemExit(2)
