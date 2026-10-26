import json
from pathlib import Path
import tempfile
import unittest

from haiagent.demo import ScriptedClient
from haiagent.executor import Result
from haiagent.protocol import Config, Task
from haiagent.runtime import build_messages, run
from haiagent.semantic import action_profile, delivery_progress
from haiagent.storage import read_trace
from terminal_context import TaskContext, TerminalEvent
from terminal_context.stagnation import observation_fingerprint


class SemanticMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'ws'
        self.workspace.mkdir()

    @staticmethod
    def action(index, **extra):
        value = {
            'action': 'run',
            'argv': ['bash', '-lc', f'python /tmp/opt{index}.py --mode search'],
            'strategy': 'search candidate configuration',
            'subgoal': 'find a viable candidate',
        }
        value.update(extra)
        return value

    def test_temp_wrappers_share_direction_but_unrelated_bash_does_not(self):
        first = action_profile(self.action(199), self.workspace)
        second = action_profile(self.action(200), self.workspace)
        unrelated = action_profile({
            'action': 'run', 'argv': ['bash', '-lc', 'rg TODO src'],
            'strategy': 'inspect outstanding work', 'subgoal': 'locate TODOs'}, self.workspace)
        self.assertEqual(first['direction_key'], second['direction_key'])
        self.assertEqual(first['action_key'], second['action_key'])
        self.assertEqual(first['tool_chain'], ['python'])
        self.assertNotEqual(first['direction_key'], unrelated['direction_key'])
        self.assertEqual(unrelated['tool_chain'], ['rg'])

    def test_argument_boundaries_full_payload_and_stdin_are_not_collapsed(self):
        joined = action_profile({'action': 'run', 'argv': ['python', 'a b']},
                                self.workspace)
        split = action_profile({'action': 'run', 'argv': ['python', 'a', 'b']},
                               self.workspace)
        self.assertNotEqual(joined['direction_key'], split['direction_key'])
        self.assertNotEqual(joined['action_key'], split['action_key'])
        prefix = 'x' * 200
        left = action_profile({'action': 'run', 'argv': ['python', '-c', prefix + 'A']},
                              self.workspace)
        right = action_profile({'action': 'run', 'argv': ['python', '-c', prefix + 'B']},
                               self.workspace)
        self.assertNotEqual(left['direction_key'], right['direction_key'])
        stdin_left = action_profile({'action': 'run', 'argv': ['python', '-'],
                                     'stdin': 'print(1)'}, self.workspace)
        stdin_right = action_profile({'action': 'run', 'argv': ['python', '-'],
                                      'stdin': 'print(2)'}, self.workspace)
        self.assertNotEqual(stdin_left['direction_key'], stdin_right['direction_key'])

    def test_different_file_regions_and_search_patterns_are_distinct_directions(self):
        commands = [
            ['bash', '-lc', "sed -n '1,120p' src/main.py"],
            ['bash', '-lc', "sed -n '121,240p' src/main.py"],
            ['bash', '-lc', 'rg first_pattern src/main.py'],
            ['bash', '-lc', 'rg second_pattern src/main.py'],
            ['python', 'reader.py', '--offset', '0', '--limit', '100'],
            ['python', 'reader.py', '--offset', '100', '--limit', '100'],
        ]
        profiles = [action_profile({'action': 'run', 'argv': argv}, self.workspace)
                    for argv in commands]
        self.assertEqual(len({profile['direction_key'] for profile in profiles}),
                         len(profiles))
        self.assertEqual(profiles[0]['targets'], profiles[1]['targets'])
        self.assertNotEqual(profiles[0]['exploration_scope'],
                            profiles[1]['exploration_scope'])

    def test_distinct_observations_without_workspace_edits_remain_exploration(self):
        context = TaskContext('different-regions', 'inspect a large file')
        for index in range(8):
            context.observe(TerminalEvent(
                task_id='different-regions', command='python streaming_reader.py',
                stdout=f'new region {index}', exit_code=0, cwd='/app',
                workspace='W', workspace_before='W', environment='E',
                direction_key='a' * 64,
                direction_summary='inspect streaming source',
                direction_targets=('large.txt',)))
        snapshot = context.snapshot()
        self.assertFalse(snapshot['memories'])
        self.assertEqual(snapshot['directions'][0]['status'], 'active')
        self.assertEqual(snapshot['directions'][0]['unique_observations'], 8)

    def test_reading_many_regions_of_one_file_never_triggers_intervention(self):
        actions = [{
            'action': 'run',
            'argv': ['bash', '-lc', f"sed -n '{start},{start + 99}p' large.txt"],
            'strategy': 'inspect another file region',
            'subgoal': 'understand the complete large file',
        } for start in range(1, 1001, 100)]
        client = ScriptedClient(actions + [{'action': 'submit', 'summary': 'inspection complete'}])

        class Executor:
            def execute(_, decision, deadline):
                return Result(0, stdout='region contains no matching marker')

        result = run(Task('region-scan', 'Inspect large.txt', self.workspace,
                          delivery='terminal'), Config(), client,
                     self.root / 'out', executor=Executor())
        trace = read_trace(self.root / 'out' / 'events.jsonl')
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'], 10)
        self.assertFalse(any(row['event'] == 'memory_intervention' for row in trace))
        self.assertFalse(any(row['event'] == 'automatic_memory' and
                             str(row.get('conclusion', '')).startswith("The direction '")
                             for row in trace))

    def test_temp_names_in_feedback_do_not_hide_same_observation(self):
        first = observation_fingerprint(0, 'analysed /tmp/opt199.py: no candidate', '', None)
        second = observation_fingerprint(0, 'analysed /tmp/opt200.py: no candidate', '', None)
        changed = observation_fingerprint(0, 'analysed /tmp/opt200.py: candidate found', '', None)
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_semantic_loop_is_intercepted_and_changed_direction_is_followed(self):
        repeated = [self.action(i) for i in (199, 200, 201, 202)]
        alternative = {
            'action': 'run', 'argv': ['bash', '-lc', 'rg TODO src'],
            'strategy': 'inspect source annotations', 'subgoal': 'find a viable candidate'}
        client = ScriptedClient(repeated + [alternative, {'action': 'submit', 'summary': 'best state'}])

        class Executor:
            def execute(_, decision, deadline):
                command = ' '.join(decision['argv'])
                if 'opt' in command:
                    name = command.split('/tmp/', 1)[1].split()[0]
                    return Result(0, stdout=f'analysed /tmp/{name}: no candidate')
                return Result(0, stdout='src/main.py:12: TODO')

        result = run(Task('semantic-loop', 'Create result.txt', self.workspace,
                          delivery='terminal'), Config(), client,
                     self.root / 'out', executor=Executor())
        trace = read_trace(self.root / 'out' / 'events.jsonl')
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'], 4)
        self.assertEqual(sum(row['event'] == 'memory_intervention' for row in trace), 1)
        visible = json.loads(client.requests[4][1]['content'])['context']
        self.assertTrue(visible['memory_intervention']['memory_ids'])
        self.assertTrue(visible['task_memory'])
        reconsideration = next(row for row in trace
                               if row['event'] == 'memory_reconsideration')
        self.assertTrue(reconsideration['changed_direction'])
        followup = next(row for row in trace if row['event'] == 'memory_followup_outcome')
        self.assertEqual(followup['action_kind'], 'run')
        self.assertTrue(followup['outcome_observed'])

    def test_citing_intervention_allows_one_audited_deliberate_override(self):
        outer = self

        class Client:
            model = 'adaptive-offline-no-API'
            def __init__(self):
                self.count = 0
                self.requests = []
                self.memory_ids = []
            def complete(self, messages, deadline, recorder):
                self.requests.append(messages)
                if self.count < 4:
                    decision = outer.action(300 + self.count)
                elif self.count == 4:
                    block = json.loads(messages[1]['content'])['context']['memory_intervention']
                    self.memory_ids = block['memory_ids']
                    decision = outer.action(304, uses_memory=self.memory_ids)
                elif self.count == 5:
                    decision = outer.action(305, uses_memory=self.memory_ids)
                else:
                    decision = {'action': 'submit', 'summary': 'bounded override completed'}
                self.count += 1
                return {'content': json.dumps(decision), 'complete': True}

        class Executor:
            def execute(_, decision, deadline):
                name = ' '.join(decision['argv']).split('/tmp/', 1)[1].split()[0]
                return Result(0, stdout=f'analysed /tmp/{name}: no candidate')

        client = Client()
        result = run(Task('memory-override', 'Create result.txt', self.workspace,
                          delivery='terminal'), Config(), client,
                     self.root / 'out', executor=Executor())
        trace = read_trace(self.root / 'out' / 'events.jsonl')
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'], 4)
        report = next(row for row in trace if row['event'] == 'memory_use_self_report')
        self.assertTrue(report['memory_ids'])
        reconsideration = next(row for row in trace
                               if row['event'] == 'memory_reconsideration')
        self.assertFalse(reconsideration['changed_direction'])
        self.assertEqual(sum(row['event'] == 'memory_intervention' for row in trace), 2)
        self.assertTrue(any(row['event'] == 'memory_override_exhausted' for row in trace))

    def test_reason_cannot_bypass_semantic_loop_by_renaming_temp_files(self):
        reason = 'Poll this generated candidate twice for a bounded asynchronous update.'
        client = ScriptedClient(
            [self.action(i) for i in (400, 401, 402)] +
            [self.action(i, retry_reason=reason) for i in (403, 404, 405)] +
            [{'action': 'submit', 'summary': 'bounded retries ended'}])

        class Executor:
            def execute(_, decision, deadline):
                name = ' '.join(decision['argv']).split('/tmp/', 1)[1].split()[0]
                return Result(0, stdout=f'analysed /tmp/{name}: still pending')

        result = run(Task('semantic-reason-bound', 'Create result.txt', self.workspace,
                          delivery='terminal'), Config(max_explained_retries=2), client,
                     self.root / 'out', executor=Executor())
        trace = read_trace(self.root / 'out' / 'events.jsonl')
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'], 5)
        self.assertEqual(sum(row['event'] == 'memory_override_reason' for row in trace), 2)
        self.assertEqual(sum(row['event'] == 'memory_override_reason_exhausted'
                             for row in trace), 1)
        self.assertEqual(sum(row['event'] == 'memory_intervention' for row in trace), 1)

    def test_total_memory_intervention_limit_fails_closed(self):
        client = ScriptedClient([self.action(i) for i in range(500, 506)])

        class Executor:
            def execute(_, decision, deadline):
                name = ' '.join(decision['argv']).split('/tmp/', 1)[1].split()[0]
                return Result(0, stdout=f'analysed /tmp/{name}: no progress')

        result = run(Task('intervention-limit', 'Create result.txt', self.workspace,
                          delivery='terminal'),
                     Config(max_memory_interventions=1,
                            max_consecutive_memory_blocks=5),
                     client, self.root / 'out', executor=Executor())
        trace = read_trace(self.root / 'out' / 'events.jsonl')
        self.assertFalse(result['submitted'])
        self.assertEqual(result['stop_reason'], 'stagnation_limit')
        self.assertEqual(result['tool_calls'], 3)
        self.assertEqual(sum(row['event'] == 'memory_intervention' for row in trace), 1)
        self.assertTrue(any(row['event'] == 'failure' and
                            row.get('intervention_limit') == 1 for row in trace))

    def test_delivery_panel_and_budget_pressure_are_bounded_observations(self):
        task = Task('delivery', 'Create reports/final.json', self.workspace,
                    delivery='terminal')
        before = delivery_progress(self.workspace, task.instruction)
        self.assertEqual(before['total'], 1)
        self.assertEqual(before['existing'], 0)
        (self.workspace / 'reports').mkdir()
        (self.workspace / 'reports' / 'final.json').write_text('{}', encoding='utf-8')
        after = delivery_progress(self.workspace, task.instruction)
        self.assertEqual(after['existing'], 1)
        self.assertIn('not correctness', after['semantics'])
        messages, _, _ = build_messages(
            task, Config(), TaskContext(task.task_id, 'deliver'), [], None,
            {'turns': 8, 'tools': 8, 'wall_seconds': 10, 'used_ratio': .9})
        protected = json.loads(messages[1]['content'])
        self.assertEqual(protected['budget_pressure']['stage'], 'preserve_and_deliver')
        self.assertEqual(protected['delivery_progress']['existing'], 1)


if __name__ == '__main__':
    unittest.main()
