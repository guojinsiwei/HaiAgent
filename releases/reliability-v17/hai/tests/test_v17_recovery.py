import json
from pathlib import Path
import tempfile
import unittest
from haiagent.demo import ScriptedClient
from haiagent.executor import Result
from haiagent.protocol import Config, Task
from haiagent.runtime import run, observation_cwd
from haiagent.cli import run_exit_code
from haiagent.storage import read_trace
from terminal_context import TaskContext, TerminalEvent


class RecoveryTests(unittest.TestCase):
    def test_context_projection_does_not_clear_subdirectory_counts(self):
        context = TaskContext('T', 'inspect')
        for i in range(4):
            context.observe(TerminalEvent('T', 'read', stdout='same', exit_code=0,
                cwd='/app/sub', workspace='W', workspace_before='W'))
            context.set_scope(cwd='/app', workspace='W')
        self.assertTrue(context.repeat_advice('read', '/app/sub', ''))
        self.assertIsNone(context.repeat_advice('read', '/app/other', ''))
        context.set_scope(cwd='/app', workspace='NEW')
        self.assertIsNone(context.repeat_advice('read', '/app/sub', ''))

    def exercise(self, *, recover=False, polling=False, method='hai'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); workspace = root / 'ws'; workspace.mkdir()
            class Executor:
                def resolve_cwd(self, cwd):
                    return workspace if cwd == '/app' else workspace / cwd
                def execute(self, command, deadline):
                    return Result(0, stdout='new evidence' if command['argv'] == ['alternative'] else 'same')
            action = {'action': 'run', 'argv': ['inspect'], 'cwd': '/app'}
            if polling:
                action['retry_reason'] = 'Poll once for an external change in the data source.'
            actions = [action] * (5 if recover else 50)
            if recover:
                actions += [{'action': 'run', 'argv': ['alternative'], 'cwd': '/app'},
                            {'action': 'submit', 'summary': 'done'}]
            client = ScriptedClient(actions)
            result = run(Task('T', 'inspect', workspace, delivery='terminal'),
                Config(method=method, max_turns=40, max_tools=40), client, root/'out', executor=Executor())
            return result, client.requests, read_trace(root/'out/events.jsonl')

    def test_583_repeats_become_bounded_recovery_not_800_calls(self):
        result, requests, events = self.exercise()
        self.assertEqual(result['stop_reason'], 'stagnation')
        self.assertEqual(result['tool_calls'], 3)
        self.assertEqual(result['interaction_rounds'], 9)
        self.assertFalse(result['submitted'])
        self.assertIsNone(result['success'])
        self.assertEqual(run_exit_code(result), 3)
        self.assertTrue(any(e['event'] == 'automatic_memory' for e in events))
        self.assertTrue(any(e['event'] == 'stagnation_recovery' and e['recovery_stage'] == 'strategy_reset' for e in events))

    def test_strategy_switch_can_recover_and_submit(self):
        result, requests, events = self.exercise(recover=True)
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'], 4)
        self.assertEqual(result['interaction_rounds'], 7)
        notice = json.loads(requests[5][1]['content'])['latest_notice']
        self.assertEqual(notice['recovery_stage'], 'strategy_reset')

    def test_retry_reason_is_not_an_unlimited_bypass(self):
        result, _, _ = self.exercise(polling=True)
        self.assertEqual(result['stop_reason'], 'stagnation')
        self.assertEqual(result['tool_calls'], 5)
        self.assertEqual(result['interaction_rounds'], 11)

    def test_raw_has_no_memory_or_recovery_intervention(self):
        result, _, events = self.exercise(method='raw')
        self.assertEqual(result['tool_calls'], 40)
        self.assertEqual(result['stop_reason'], 'turn_budget')
        self.assertFalse(any(e['event'] == 'stagnation_recovery' for e in events))

    def test_alias_resolution_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp).resolve()
            with self.assertRaises(ValueError):
                observation_cwd(object(), ws, '..')

    def test_binary_rejection_keeps_conversation_and_cumulative_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ws=root/'ws';ws.mkdir();seen=[]
            client=ScriptedClient([{'action':'submit','summary':'first'}, {'action':'submit','summary':'second'}])
            def feedback(artifact):
                seen.append(artifact)
                return 'Rejected' if len(seen)==1 else None
            result=run(Task('T','task',ws,delivery='terminal'),Config(),client,root/'out',submission_feedback=feedback)
            self.assertTrue(result['submitted'])
            self.assertEqual(result['interaction_rounds'],2)
            self.assertEqual(json.loads(client.requests[-1][1]['content'])['latest_notice']['submission_rejected'],'Rejected')
