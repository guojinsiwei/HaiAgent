"""Deterministic memory-to-action example, using the unchanged current core.

This is a mock workspace demonstration, NOT a benchmark result or security sandbox.
"""
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT


def main():
    environment = FakeEnvironment()
    environment.dependencies['config.txt'] = 'file:v1'
    memory = dict(kind='blocker', conclusion='Parsing this unchanged config failed',
        condition='while config.txt remains unchanged', operation='parse-config',
        targets=['config.txt'], next_step='Inspect its encoding first', evidence_ids=['E1'])
    # The matching parse action is proposed but not executed. The next model
    # response sees a memory intervention and switches to creating a deliverable.
    actions = [run_action('read', 'config.txt'),
        dict(action='checkpoint', label='evidence', hypothesis='retain', memory=memory),
        run_action('python', 'parse-config', 'config.txt'),
        run_action('artifact', 'result.json', 'v1'), SUBMIT]
    with tempfile.TemporaryDirectory(prefix='bestfgs-reader-demo-') as temporary:
        runner = LeanTaskRunner(environment, Scripted(actions), Scripted([]),
            LeanConfig(max_turns=30, max_tools=20, max_advisor_calls=0,
                       memory_reliability=True, outcome_reliability=True),
            Path(temporary)/'trace')
        result = runner.run(TaskSpec('memory-demo', 'Create useful output'))
        counts = result['mechanism_utilization']
        assert result['submitted'] and counts['memory_action_changed'] == 1
        assert ['python', 'parse-config', 'config.txt'] not in [a['argv'] for a in environment.executed]
        print(json.dumps(dict(submitted=result['submitted'],
            memory_interventions=counts['memory_interventions'],
            memory_action_changed=counts['memory_action_changed'],
            memory_followup_workspace_changed=counts['memory_followup_workspace_changed'],
            executed_commands=[a['argv'] for a in environment.executed],
            notice='Offline scripted example; does not prove real-model benefit'),ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
