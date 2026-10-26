import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_terminal_bench_cube as cube


class CubePilotTests(unittest.TestCase):
    def test_pinned_development_pool_and_pilot(self):
        lock = cube.locked_sources()
        self.assertEqual(sum(not t['frozen'] for t in lock['tasks']), 80)
        self.assertTrue(all(not t['frozen'] for t in lock['tasks'] if t['id'] in cube.PILOT))

    def test_manifest_relocation_and_fresh_seeds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'run'
            manifest = cube.prepare(root)
            tasks = json.loads(manifest.read_text())['tasks']
            for task in tasks:
                self.assertNotIn('/app/', task['goal'])
                self.assertEqual(list(Path(task['workspace']).iterdir()), [])
            with self.assertRaises(FileExistsError):
                cube.prepare(root)

    def test_changed_public_instruction_is_rejected(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp) / 'data'
            shutil.copytree(cube.DATA, data)
            (data / 'public_tasks' / cube.PILOT[0] / 'instruction.md').write_text('changed')
            with patch.object(cube, 'DATA', data), self.assertRaisesRegex(ValueError, 'Public source changed'):
                cube.locked_sources()

    def test_frozen_pilot_rejected(self):
        with patch.object(cube, 'PILOT', ('mailman',)), self.assertRaises(RuntimeError):
            cube.locked_sources()

    def test_missing_candidate_output_fails_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            result = cube.public_probe('polyglot-c-py', Path(temp))
            self.assertFalse(result['public_smoke_passed'])
            self.assertIsNone(result['official_reward'])

    def test_no_result_is_not_a_failure_score(self):
        with tempfile.TemporaryDirectory() as temp:
            result = cube.report(Path(temp))
            self.assertEqual(len(result['rows']), 4)
            self.assertTrue(all(r['status'] == 'not_started' and r['official_reward'] is None for r in result['rows']))

    def test_both_methods_have_identical_budgets_and_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            args = type('Args', (), {'output_root': Path(temp) / 'pilot', 'model': 'test-model'})()
            ready = {'ready_for_portable_pilot': True, 'implementation_sha256': 'code', 'dataset_lock_sha256': 'data'}
            with patch.object(cube, 'preflight', return_value=ready), patch.dict(cube.os.environ, {'DEEPSEEK_API_KEY': 'test-only'}), patch.object(cube.run_notebook, 'main', return_value=0) as runner:
                self.assertEqual(cube.run(args), 0)
            calls = [call.args[0] for call in runner.call_args_list]
            self.assertEqual(len(calls), 2)
            tails = [c[c.index('--') + 1:] for c in calls]
            self.assertEqual(tails[0], tails[1])
            self.assertIn('--comparison-metrics', tails[0])
            self.assertNotIn('test-only', (args.output_root / 'pilot-protocol.json').read_text())


if __name__ == '__main__':
    unittest.main()
