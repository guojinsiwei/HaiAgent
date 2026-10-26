import ast
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'sources'), str(ROOT / 'sources/bestfgs-project/src'),
               str(ROOT / 'sources/hai-project/src'), str(ROOT / 'sources/bestfgs-project/tests')]
from bestfgs.prompt_views import classify, diagnostic_category
from bestfgs.lean_protocol import ADVISOR_SYSTEM, ACTION_SYSTEM, validate_evidence_ids
from bestfgs.lean_memory import Memories
from hai_outcomes import classify as outcome
from terminal_context.core import TaskContext, size
from terminal_context.types import TerminalEvent
import test_lean
from test_lean import run_action, SUBMIT


class Repairs(unittest.TestCase):
    def test_shell_diagnostic_and_compression_are_independent(self):
        for script in ('cd /app && cat file.txt', 'cd /app && cat "file name.txt" | head -n 2',
                       'cd /app && rg pattern src', "sed -n '1,120p' file.txt"):
            with self.subTest(script=script):
                self.assertNotEqual(diagnostic_category(['bash', '-lc', script]), 'generic')
        self.assertEqual(classify(['bash', '-lc', 'cd /app && cat file.txt']), 'generic')

    def test_shell_unknown_and_writing_commands_stay_generic(self):
        for script in ('cat f > g', 'cat f; touch g', 'cat $(touch f)', 'cat `touch f`',
                       'cd /app && python script.py', 'find . -delete', 'find . -exec cat {} +',
                       'rg --pre=helper pattern file', 'git diff --output=patch', "sed -i 's/a/b/' f",
                       "sed 'e touch /tmp/a' f", 'cat f &&', 'cd /app', 'bash -c "cat f"',
                       'cat f\ncat g', 'cd /app || cat f'):
            with self.subTest(script=script):
                self.assertEqual(diagnostic_category(['bash', '-lc', script]), 'generic')

    def test_wrapped_read_reaches_advisor(self):
        fixture = test_lean.LeanTests()
        try:
            result = fixture.exercise([run_action('bash', '-lc', 'cd /app && cat file.txt')]*14+[SUBMIT],
                                      [dict(alternatives=[])])
            self.assertEqual(result[0]['advisor_rounds'], 1)
        finally:
            fixture.doCleanups()

    def test_evidence_contract_and_unknown_ids(self):
        self.assertIn('at most 3 IDs', ADVISOR_SYSTEM)
        self.assertIn('1 to 3 IDs', ACTION_SYSTEM)
        visible = {'E1', 'E2', 'E3', 'E4'}
        self.assertEqual(validate_evidence_ids(['E1', 'E2', 'E3'], visible), ['E1', 'E2', 'E3'])
        with self.assertRaisesRegex(ValueError, 'at most 3'):
            validate_evidence_ids(sorted(visible), visible)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            validate_evidence_ids(['E99'], visible)
        with self.assertRaisesRegex(ValueError, 'at least 1'):
            validate_evidence_ids([], visible, minimum=1)
        with self.assertRaisesRegex(ValueError, 'a list'):
            validate_evidence_ids(None, visible)

    def test_memory_still_rejects_fabricated_evidence(self):
        value = dict(conclusion='fixture', condition='fixture', evidence_ids=['E99'])
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            Memories().admit(value, {'E1': {'after': 'same'}}, {'E1'}, lambda _: {})

    def test_actual_linear_adapter_cwd_mapping(self):
        # Load exactly the production class without importing optional Harbor.
        tree = ast.parse((ROOT / 'sources/hai_transport.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LinearExecutor')
        module = ast.Module(body=[node], type_ignores=[])
        namespace = dict(Path=Path, shutil=shutil, os=os)
        exec(compile(module, 'hai_transport.py', 'exec'), namespace)
        adapter = namespace['LinearExecutor'].__new__(namespace['LinearExecutor'])
        adapter.workspace = Path('/private/mirror/live')
        self.assertEqual(adapter.observation_cwd({'cwd': '/app'}), '/private/mirror/live')
        self.assertEqual(adapter.observation_cwd({'cwd': '.'}), '/private/mirror/live')
        self.assertEqual(adapter.observation_cwd({'cwd': '/app/sub'}), '/private/mirror/live/sub')
        self.assertEqual(adapter.observation_cwd({'cwd': 'sub'}), '/private/mirror/live/sub')
        self.assertEqual(adapter.observation_cwd({'cwd': '/app2'}), '/app2')

    def context(self):
        context = TaskContext('large-memory', 'find viable candidate')
        cwd = '/var/tmp/' + 'isolated-integration-test/' * 5 + 'live'
        for i in range(3):
            context.observe(TerminalEvent(task_id='large-memory', command=f'python /tmp/opt{200+i}.py',
                stdout='no viable candidate; ' + 'detail ' * 270, exit_code=0,
                cwd=cwd, workspace='a'*64, workspace_before='a'*64,
                direction_key='b'*64, direction_summary='search candidate configuration'))
        return context

    def test_large_memory_visible_without_storage_or_budget_change(self):
        context = self.context()
        before = copy.deepcopy(context.snapshot()['memories'])
        self.assertGreater(size([before[0]]), 3000)
        view = context.build_prompt(max_units=12000, include_feedback=False, query='candidate')
        shown = json.loads(view.content)['task_memory']
        self.assertTrue(shown)
        self.assertLessEqual(size(shown), 3000)
        self.assertLessEqual(len(view.content.encode()), 12000)
        self.assertEqual(before, context.snapshot()['memories'])
        self.assertEqual(shown[0]['conclusion'], before[0]['conclusion'])
        self.assertEqual(shown[0]['applies_when'], before[0]['applies_when'])
        self.assertEqual(shown[0]['evidence_ids'], [e['id'] for e in before[0]['evidence']])
        self.assertEqual(shown[0]['validity'], 'current')
        self.assertEqual(shown[0]['scope'], before[0]['scope'])

    def test_compact_historical_memory_remains_historical(self):
        context = self.context()
        context.set_scope(cwd='/different', workspace='a'*64, environment=None)
        shown = json.loads(context.build_prompt(max_units=12000, include_feedback=False, query='candidate').content)['task_memory']
        self.assertTrue(shown)
        self.assertEqual(shown[0]['validity'], 'stale')
        self.assertEqual(shown[0]['use_mode'], 'historical_reference')

    def test_outcomes_ignore_only_observability_between_error_and_deadline(self):
        official = dict(process_exit_code=0, verifier_result={}, exception_info=None)
        ending = dict(event='method_end', result=dict(stop_reason='wall_budget'))
        for between, code, expected in ((['mechanism_utilization'], None, True),
                                         (['tool_start'], None, False),
                                         (['mechanism_utilization'], 'http_401', False),
                                         (['mechanism_utilization'], 'http_429', False)):
            events = [dict(event='model_error', error_code=code)] + [dict(event=e) for e in between] + [ending]
            self.assertEqual(outcome(official, events)['infrastructure_ok'], expected)
        events = [dict(event='method_end', result=dict(stop_reason='infrastructure_error'))]
        self.assertFalse(outcome(official, events)['infrastructure_ok'])
        self.assertTrue(outcome(official, [dict(event='method_end', stop_reason='submit')])['infrastructure_ok'])


if __name__ == '__main__':
    unittest.main()
