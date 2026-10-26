import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / 'hai-project/src'), str(HERE / 'bestfgs-project/src')]
from audit import Audit, verify
from prepare import select
from resources import fits
from haiagent.demo import ScriptedClient
from haiagent.protocol import Task, Config
from haiagent.runtime import run

class AdaptationTests(unittest.TestCase):
    def test_hai_memory_survives_official_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / 'workspace'
            workspace.mkdir()
            client = ScriptedClient([
                {'action': 'run', 'argv': [sys.executable, '-c', "print('fixture token is ready')"]},
                {'action': 'submit', 'summary': 'first', 'memory': {
                    'conclusion': 'fixture token is ready', 'applies_when': 'same workspace in this task',
                    'evidence_ids': ['E1'], 'kind': 'finding', 'dependencies': ['workspace']}},
                {'action': 'submit', 'summary': 'second'},
            ])
            seen = []
            def feedback(artifact):
                seen.append(artifact)
                return 'Submission rejected; continue.' if len(seen) == 1 else None
            output = Path(tmp) / 'run'
            result = run(Task('memory-retention', 'Check the fixture token', workspace, delivery='terminal'),
                         Config(method='hai', max_turns=4, max_tools=2), client, output,
                         submission_feedback=feedback)
            events = [json.loads(line) for line in (output / 'events.jsonl').read_text().splitlines()]
            requests = [row for row in events if row.get('event') == 'request_context']
            self.assertTrue(result['submitted'])
            self.assertEqual(result['interaction_rounds'], 3)
            self.assertEqual(result['tool_calls'], 1)
            self.assertGreaterEqual(requests[-1]['memory_count'], 1)

    def test_selection_is_twelve_fixed_pairs(self):
        manifest = json.loads((HERE / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(manifest['tasks']), 12)
        self.assertEqual(manifest['total_trials'], 36)
        self.assertEqual(len({t['task'] for t in manifest['tasks']}), 12)
        for task in manifest['tasks']:
            self.assertTrue(fits([task] * 3))
        self.assertFalse(fits([manifest['tasks'][0]] * 4))

    def test_secret_redaction_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.jsonl'
            audit = Audit(path, ['not-a-real-key'])
            audit.emit('request', text='Bearer not-a-real-key', api_key='other-value')
            audit.emit('response', value=3)
            self.assertEqual(verify(path)['events'], 2)
            self.assertNotIn('not-a-real-key', path.read_text())
            self.assertNotIn('other-value', path.read_text())
            path.write_text(path.read_text().replace('"value":3', '"value":4'))
            with self.assertRaises(ValueError):
                verify(path)

    def test_hai_and_raw_continue_without_restarting_budgets(self):
        for method in ('hai', 'raw'):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as tmp:
                workspace = Path(tmp) / 'workspace'
                workspace.mkdir()
                prompts = []
                class Client(ScriptedClient):
                    def complete(self, messages, deadline, recorder):
                        prompts.append(messages)
                        return super().complete(messages, deadline, recorder)
                client = Client([{'action': 'submit', 'summary': 'first'},
                                 {'action': 'submit', 'summary': 'second'}])
                seen = []
                def feedback(artifact):
                    seen.append(artifact)
                    return 'Submission did not pass. Continue working.' if len(seen) == 1 else None
                result = run(Task('offline-continuation', 'Create the requested file', workspace, delivery='terminal'),
                             Config(method=method, max_turns=3, max_tools=2), client,
                             Path(tmp) / 'run', submission_feedback=feedback)
                self.assertTrue(result['submitted'])
                self.assertEqual(result['interaction_rounds'], 2)
                self.assertEqual(len(seen), 2)
                self.assertIn('Submission did not pass', json.dumps(prompts[1]))
                self.assertEqual(result['tool_calls'], 0)

if __name__ == '__main__':
    unittest.main()
