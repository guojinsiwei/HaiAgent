"""Linux scheduler tests; no Docker operations, network or real credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import control
from types import SimpleNamespace
from unittest.mock import Mock


class ControlTests(unittest.TestCase):
    def test_long_command_token_is_not_a_file(self):
        from bestfgs.semantic import _candidate_workspace_paths
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'valid.py').touch()
            snapshot = SimpleNamespace(location=tmp)
            outcome = SimpleNamespace(parent_snapshot=snapshot, resulting_snapshot=snapshot)
            found = _candidate_workspace_paths(['A' * 2048 + '.py', 'valid.py'], outcome)
            self.assertIn('valid.py', found)
            self.assertEqual(len(found), 1)

    def test_expired_budget_does_not_launch_container(self):
        from docker_state import DockerState, WorkBudgetExhausted
        state = object.__new__(DockerState)
        state.reserve = Mock()
        state.docker = Mock()
        state.deadline = 0
        with self.assertRaises(WorkBudgetExhausted):
            state.branch(None)
        state.docker.assert_not_called()

    def test_budget_delivery_uses_owned_checkpoint_candidate(self):
        from transport import budget_candidate
        with tempfile.TemporaryDirectory() as tmp:
            initial = SimpleNamespace(location=tmp + '/root')
            selected = SimpleNamespace(location=tmp + '/chosen')
            state = SimpleNamespace(initial=initial, snapshots={'s': {'snapshot': selected}})
            checkpoint = Path(tmp) / 'graph.json'
            self.assertIs(budget_candidate(state, checkpoint), initial)
            checkpoint.write_text(json.dumps({'best_workspace': selected.location}))
            self.assertIs(budget_candidate(state, checkpoint), selected)
            checkpoint.write_text(json.dumps({'best_workspace': '/not-owned'}))
            with self.assertRaises(RuntimeError):
                budget_candidate(state, checkpoint)

    def exercise(self, fail):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = [{'task': 'task-' + str(i)} for i in range(12)]
            (root / 'manifest.json').write_text(json.dumps({'tasks': tasks}))
            private = root / 'test-input'
            private.mkdir()
            credential = private / 'placeholder'
            credential.write_text('fixture-placeholder-not-a-real-credential')
            calls = []
            def execute(row, method):
                calls.append((row['task'], method))
                if fail:
                    raise RuntimeError('Synthetic infrastructure failure')
                trial = root / (row['task'] + '-' + method)
                (trial / 'agent').mkdir(parents=True)
                (trial / 'agent/audit.jsonl').touch()
                return {'report': str(trial / 'result.json'), 'process_exit_code': 0,
                        'exception_info': None, 'method': method, 'task': row['task']}
            with patch.object(control, 'HERE', root), patch.object(control, 'reserve'), \
                 patch.object(control, 'validate', return_value={'protocol_sha256': 'fixture'}), \
                 patch.object(control, 'execute', side_effect=execute):
                control.run_all(str(credential))
                with self.assertRaises(RuntimeError):
                    control.run_all(str(credential))
            health = json.loads((root / 'health.json').read_text())
            self.assertFalse(credential.exists())
            self.assertEqual(health['active'], [])
            if fail:
                self.assertLessEqual(len(calls), 3)
                self.assertEqual(health['state'], 'needs_attention')
                self.assertGreaterEqual(health['pending'], 33)
            else:
                self.assertEqual(len(set(calls)), 36)
                self.assertEqual(health['state'], 'completed')
                self.assertEqual(health['completed'], 36)

    def test_complete_once(self):
        self.exercise(False)

    def test_stop_dispatch_on_infrastructure_failure(self):
        self.exercise(True)


if __name__ == '__main__':
    unittest.main()
