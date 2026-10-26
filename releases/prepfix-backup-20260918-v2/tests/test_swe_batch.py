from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_swe_batch
import evaluate_swe_batch as evaluate
import swe_batch
from benchmark_runtime import atomic_write_json, canonical_sha256
from benchmark_splits import frozen_swebench_ids
from run_notebook import export_swe_patch, load_tasks, tree_digest


def task(identity='sympy__sympy-16450'):
    return {'instance_id': identity, 'repo': 'sympy/sympy', 'base_commit': 'a' * 40,
            'version': '1.5', 'problem_statement': 'public issue',
            'recipe': {'cached_environment_yml': 'name: testbed\nchannels:\n  - defaults\ndependencies:\n  - python=3.9\nprefix: /opt/miniconda3/envs/testbed\n'}}


def plan(tasks=None):
    tasks = tasks or [task()]
    value = {'schema_version': 1, 'dataset': 'SWE-bench/SWE-bench_Verified', 'split': 'test',
             'count': len(tasks), 'tasks': tasks, 'harness_commit': 'b' * 40, 'dataset_fingerprint': 'data'}
    value['plan_sha256'] = canonical_sha256(value)
    return value


class BatchTests(unittest.TestCase):
    def test_selection_is_deterministic_and_excludes_protected(self):
        first, pool = build_swe_batch.select_ids(['c', 'a', 'b', 'd'], 2, 17, {'b'})
        second, _ = build_swe_batch.select_ids(['d', 'b', 'a', 'c'], 2, 17, {'b'})
        self.assertEqual(first, second)
        self.assertNotIn('b', first)
        self.assertEqual(pool, ['a','c','d'])

    def test_shipped_plan_has_100_public_nonfrozen_unique_tasks(self):
        p = swe_batch.load_plan(swe_batch.ROOT / 'examples/swe100-plan.json')
        ids = [t['instance_id'] for t in p['tasks']]
        self.assertEqual(len(ids), 100)
        self.assertFalse(set(ids) & set(frozen_swebench_ids()))
        self.assertNotIn('sympy__sympy-16450', ids)
        for t in p['tasks']:
            self.assertNotIn('test_patch', t)
            self.assertNotIn('patch', t)
            self.assertNotIn('FAIL_TO_PASS', t)
            self.assertTrue(swe_batch.environment_yaml(t['recipe']))
            swe_batch.safe_preinstall(t)

    def test_plan_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = plan()
            p['count'] = 100
            path = Path(tmp) / 'plan.json'
            atomic_write_json(path, p)
            with self.assertRaises(ValueError):
                swe_batch.load_plan(path)

    def test_environment_retains_pins_not_container_prefix(self):
        text = swe_batch.environment_yaml(task()['recipe'])
        self.assertIn('python=3.9', text)
        self.assertIn('defaults', text)
        self.assertNotIn('prefix:', text)
        self.assertNotIn('name:', text)

    def test_unsafe_upstream_setup_not_executed(self):
        t = task()
        t['recipe']['pre_install'] = ['apt-get upgrade -y']
        with self.assertRaises(ValueError):
            swe_batch.safe_preinstall(t)

    def make_bundle(self, root, states):
        p = plan([task(s['id']) for s in states])
        atomic_write_json(root / 'batch.json', {'plan_sha256': p['plan_sha256']})
        for state in states:
            atomic_write_json(root / 'states' / (state['id'] + '.json'), state)
            if state['status'] == 'completed':
                row = {'instance_id': state['id'], 'model_name_or_path': 'deepseek-flash', 'model_patch': 'diff'}
                path = root / 'search' / state['id'] / 'predictions.jsonl'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(row) + '\n', encoding='utf-8')
        swe_batch.export_bundle(root, p)
        return p

    def test_export_includes_failed_tasks_as_empty_without_shrinking_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root, [{'id':'sympy__sympy-16450','status':'completed'},
                                    {'id':'sample__sample-1','status':'prepare_error'}])
            _, rows, states, manifest = evaluate.read_bundle(root / 'evaluation-bundle.zip')
            self.assertEqual(manifest['total'], 2)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]['model_patch'], '')
            result = evaluate.summarize(rows, states, {rows[0]['instance_id']: {'resolved':True}})
            self.assertEqual(result['summary']['resolved_rate_over_selected'], .5)
            self.assertEqual(result['summary']['empty_patch'], 1)

    def test_partial_bundle_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root, [{'id':'sympy__sympy-16450','status':'prepared'}])
            with self.assertRaises(ValueError):
                evaluate.read_bundle(root / 'evaluation-bundle.zip')
            evaluate.read_bundle(root / 'evaluation-bundle.zip', True)

    def test_bundle_modified_predictions_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_bundle(root, [{'id':'sympy__sympy-16450','status':'completed'}])
            with zipfile.ZipFile(root / 'evaluation-bundle.zip') as source:
                entries = {name: source.read(name) for name in source.namelist()}
            entries['predictions.jsonl'] += b' '
            with zipfile.ZipFile(root / 'tampered.zip', 'w') as archive:
                for name, data in entries.items():
                    archive.writestr(name, data)
            with self.assertRaises(ValueError):
                evaluate.read_bundle(root / 'tampered.zip')

    def test_duplicate_predictions_rejected(self):
        row = json.dumps({'instance_id':'sample__sample-1','model_name_or_path':'agent','model_patch':''})
        with self.assertRaises(ValueError):
            evaluate.predictions_from_text(row + '\n' + row)

    def test_empty_patch_and_test_failure_and_infrastructure_are_distinct(self):
        rows = [{'instance_id': f'r__r-{i}', 'model_patch': p} for i,p in enumerate(['diff','diff','','diff'])]
        summary = evaluate.summarize(rows, [], {'r__r-0':{'resolved':True},'r__r-1':{'resolved':False}})['summary']
        self.assertEqual([summary[k] for k in ('resolved','unresolved','empty_patch','evaluation_error')], [1,1,1,1])

    def test_failed_attempt_usage_counted(self):
        rows = [{'instance_id':'r__r-0','model_patch':''}]
        states = [{'id':'r__r-0','model_usage':{'prompt_tokens':5},'previous_attempts':[{'model_usage':{'prompt_tokens':7}}]}]
        self.assertEqual(evaluate.summarize(rows, states, {})['summary']['prompt_tokens_recorded'], 12)

    def test_completed_missing_prediction_is_not_silently_zeroed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_write_json(root / 'states/sympy__sympy-16450.json', {'id':'sympy__sympy-16450','status':'completed'})
            with self.assertRaises(ValueError):
                swe_batch.artifacts(root, plan())

    def test_status_does_not_acquire_active_runner_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self.make_bundle(root, [{'id':'sympy__sympy-16450', 'status':'searching'}])
            path = root / 'plan.json'
            atomic_write_json(path, p)
            with swe_batch.run_lock(root):
                self.assertEqual(swe_batch.main(['status', '--root', str(root), '--plan', str(path)]), 0)

    def test_runtime_error_normalized_for_export_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = 'sympy__sympy-16450'
            output = root / 'search' / identity
            attempt = root / 'attempt'
            atomic_write_json(output / identity / 'status.json', {'status':'error', 'attempt':str(attempt)})
            atomic_write_json(attempt / 'agent-result.json', {'stop_reason':'runtime_error_with_checkpoint'})
            (output / 'predictions.jsonl').write_text(json.dumps({'instance_id':identity, 'model_patch':''}))
            args = argparse.Namespace(root=root, task_timeout=10)
            with patch.object(swe_batch, 'checked'):
                result = swe_batch.search_task(task(), {'task_python':'python'}, args, [])
            self.assertEqual(result['status'], 'search_error')

    @unittest.skipUnless(os.name == 'posix', 'Preparation/search runs on Linux')
    def test_model_outage_stops_batch_before_next_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = plan([task(), task('sample__sample-1')])
            path = root / 'plan.json'
            atomic_write_json(path, p)
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY':'unit-test-not-a-real-key'}), \
                 patch('bestfgs.retrac_adapter.OpenAICompatibleJSONClient') as client, \
                 patch.object(swe_batch, 'prepare_task', return_value={}) as prepare, \
                 patch.object(swe_batch, 'search_task', return_value={'id':task()['instance_id'], 'status':'model_error'}) as search:
                client.return_value.complete_json.return_value = {'ok':True}
                client.return_value.usage_summary.return_value = {}
                self.assertEqual(swe_batch.main(['run','--root',str(root),'--plan',str(path),'--min-free-gb','0.001']), 2)
                self.assertEqual(prepare.call_count, 1)
                self.assertEqual(search.call_count, 1)
                states = json.loads((root / 'summary.json').read_text())
                self.assertEqual([s['status'] for s in states], ['model_error', 'pending'])

    @unittest.skipUnless(os.name == 'posix', 'Preparation runs on Linux')
    def test_resumed_preparation_skips_completed_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self.make_bundle(root, [{'id':'sympy__sympy-16450','status':'completed'}])
            plan_path = root / 'public.json'
            atomic_write_json(plan_path, p)
            # Test the real main loop with existing matching run config created by first prepare.
            (root / 'batch.json').unlink()
            with patch.object(swe_batch, 'prepare_task') as prepare:
                result = swe_batch.main(['prepare','--root',str(root),'--plan',str(plan_path)])
                self.assertEqual(result, 0)
                prepare.assert_not_called()

    def test_python_imports_snapshot_instead_of_editable_seed(self):
        from bestfgs.environment import ForkedWorkspaceEnvironment
        from bestfgs.models import CommandSpec
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / 'seed'
            (seed / 'src').mkdir(parents=True)
            (seed / 'src/batch_probe_module.py').write_text('value = "seed"\n')
            runtime = ForkedWorkspaceEnvironment(seed, root / 'runs')
            snap = Path(runtime.initial_snapshot().location)
            (snap / 'src/batch_probe_module.py').write_text('value = "snapshot"\n')
            (snap / 'scripts').mkdir()
            (snap / 'scripts/probe.py').write_text('import batch_probe_module; print(batch_probe_module.value)\n')
            with patch.dict(os.environ, {'BESTFGS_TASK_SOURCE_PATH':'1', 'PYTHONPATH':str(seed / 'src')}):
                result = runtime._execute_command(snap, CommandSpec(argv=(sys.executable, 'scripts/probe.py'), description='Verify snapshot source import'))
            self.assertEqual(result.return_code, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'snapshot')

    def test_preparation_commit_is_excluded_from_exported_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / 'seed'
            seed.mkdir()
            def git(*args):
                return subprocess.run(['git',*args], cwd=seed, check=True, capture_output=True, text=True).stdout.strip()
            git('init')
            git('config','user.name','test')
            git('config','user.email','test@localhost')
            (seed / 'setup.cfg').write_text('old\n')
            (seed / 'code.py').write_text('x=1\n')
            git('add','.')
            git('commit','-m','base')
            base = git('rev-parse','HEAD')
            (seed / 'setup.cfg').write_text('environment setup\n')
            git('commit','-am','setup')
            prepared = git('rev-parse','HEAD')
            manifest = root / 'manifest.json'
            atomic_write_json(manifest, {'schema_version':1,'benchmark':'swebench','tasks':[
                {'id':'sympy__sympy-16450','goal':'test','workspace':str(seed),'base_commit':base,'prepared_commit':prepared}]})
            load_tasks(manifest, root / 'output')
            (seed / 'code.py').write_text('x=2\n')
            attempt = root / 'attempt'
            attempt.mkdir()
            diff = export_swe_patch(seed, prepared, attempt)
            self.assertIn('code.py', diff)
            self.assertNotIn('setup.cfg', diff)

    @unittest.skipUnless(os.name == 'posix', 'Unix symlinks')
    def test_only_internal_seed_symlinks_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a').write_text('hello')
            (root / 'link').symlink_to('a')
            tree_digest(root)
            (root / 'escape').symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):
                tree_digest(root)


if __name__ == '__main__':
    unittest.main()
