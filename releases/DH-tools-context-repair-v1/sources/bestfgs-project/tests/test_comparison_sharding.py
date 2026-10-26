import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_comparison as paired


class ShardingTests(unittest.TestCase):
    def test_fixed_100_disjoint_balanced_and_order_independent(self):
        ids = [f'task-{i}' for i in range(100)]
        shards = paired.shard_assignments(ids, 2)
        self.assertEqual(list(map(len, shards)), [50, 50])
        self.assertEqual(set(shards[0]) | set(shards[1]), set(ids))
        self.assertFalse(set(shards[0]) & set(shards[1]))
        self.assertEqual(shards, paired.shard_assignments(ids[::-1], 2))

    def test_single_worker_preserves_original_order(self):
        self.assertEqual(paired.shard_assignments(['b', 'a'], 1), [['b', 'a']])

    def test_invalid_assignments(self):
        for ids, count in [([], 1), (['a', 'a'], 2), (['a'], 0), (['a'], 2)]:
            with self.assertRaises(ValueError):
                paired.shard_assignments(ids, count)

    def test_common_protocol_exports_all_ids_and_workers_only_run_their_pairs(self):
        ids = [f'task-{i}' for i in range(6)]
        plan = {'tasks': [{'instance_id': i} for i in ids]}
        protocol = {'expected_ids': ids, 'sharding': {'count': 2, 'workers': paired.shard_assignments(ids, 2)}}
        calls, exports = [], []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = ['run', '--prepared-root', str(root / 'prepared'), '--output-root', str(root / 'output'), '--shard-count', '2']
            with (patch.dict(os.environ, DEEPSEEK_API_KEY='test'),
                  patch.object(paired, 'load_plan', return_value=plan),
                  patch.object(paired, 'protocol_for', return_value=(protocol, dict.fromkeys(ids, {}), [])),
                  patch.object(paired, 'run_one', side_effect=lambda args, proto, method, identity, data: calls.append((args.shard_index, method, identity)) or True),
                  patch.object(paired, 'export_arms', side_effect=lambda args, p, proto: exports.append(proto)),
                  redirect_stdout(io.StringIO())):
                for index in range(2):
                    self.assertEqual(paired.main(base + ['--shard-index', str(index)]), 0)
            self.assertEqual(len(calls), 12)
            self.assertEqual(len(set((m, i) for _, m, i in calls)), 12)
            for index, method, identity in calls:
                self.assertIn(identity, protocol['sharding']['workers'][index])
            self.assertEqual(exports, [protocol, protocol])
            for index in range(2):
                state = json.loads((root / 'output/workers' / f'{index}.json').read_text())
                self.assertEqual(state['status'], 'completed')

    def test_duplicate_worker_rejected_before_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (paired.run_lock(root / 'output/worker-locks/0'),
                  patch.dict(os.environ, DEEPSEEK_API_KEY='test'),
                  patch.object(paired, 'load_plan', return_value={'tasks': [{'instance_id': 'a'}]}),
                  patch.object(paired, 'protocol_for', return_value=({'expected_ids': ['a']}, {'a': {}}, [])),
                  patch.object(paired, 'run_one') as run):
                with self.assertRaises(ValueError):
                    paired.main(['run', '--prepared-root', str(root / 'prepared'), '--output-root', str(root / 'output')])
                run.assert_not_called()

    def test_metadata_context_does_not_retry_body_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'body-error'):
                with paired.serialized_metadata(Path(tmp)):
                    raise ValueError('body-error')


if __name__ == '__main__':
    unittest.main()
