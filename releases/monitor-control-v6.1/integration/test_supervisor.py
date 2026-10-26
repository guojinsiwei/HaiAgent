import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from supervisor import Supervisor, disposition, failure_streak, read, write


class Classification(unittest.TestCase):
    def test_recovered_memory_errors_do_not_stop_dispatch(self):
        row = {'classification': {'reasons': [], 'method_issues': ['model_error']}}
        events = [{'event': 'model_error', 'role': 'memory'}, {'event': 'model_response'},
                  {'event': 'model_error', 'role': 'memory'}, {'event': 'model_response'},
                  {'event': 'method_end', 'stop_reason': 'wall_budget_exhausted'}]
        result = disposition(row, events)
        self.assertEqual(result['auxiliary_errors_recovered'], 2)
        self.assertFalse(result['trial_failure'])
        self.assertFalse(result['admission_failure'])
        self.assertEqual(result['original_method_issues'], ['model_error'])

    def test_local_failure_recorded_but_does_not_block_whole_queue(self):
        result = disposition({'needs_attention': True, 'stop_reason': 'api_error'}, [])
        self.assertTrue(result['trial_failure'])
        self.assertTrue(result['admission_failure'])
        self.assertFalse(result['blocks_dispatch'])

    def test_explicit_credentials_block(self):
        result = disposition({}, [{'event': 'model_error', 'error_code': 'provider_401'}])
        self.assertTrue(result['blocks_dispatch'])

    def test_status_only_is_not_mistaken_for_structured_credential_error(self):
        result = disposition({}, [{'event': 'model_error', 'status': '401'}])
        self.assertFalse(result['blocks_dispatch'])

    def test_streak_resets_after_healthy_trial(self):
        good = {'supervision': {'trial_failure': False, 'admission_failure': False}}
        bad = {'supervision': {'trial_failure': True, 'admission_failure': True}}
        self.assertEqual(failure_streak([bad, bad, good, bad]), 1)
        self.assertEqual(failure_streak([good, bad, bad, bad]), 3)

    def test_method_failures_do_not_trip_infrastructure_streak(self):
        method_failure = {'supervision': {'trial_failure': True, 'admission_failure': False}}
        self.assertEqual(failure_streak([method_failure, method_failure, method_failure]), 0)

    def test_unrecovered_error_remains_visible(self):
        result = disposition({'classification': {'reasons': [], 'method_issues': ['model_error']}},
                             [{'event': 'model_error', 'role': 'memory'}])
        self.assertTrue(result['trial_failure'])
        self.assertFalse(result['admission_failure'])
        self.assertFalse(result['blocks_dispatch'])

    def test_disk_admission_pauses_before_executor_floor_and_recovers(self):
        instance = Supervisor.__new__(Supervisor)
        instance.root, instance.kind = Path('/fixture'), 'college'
        instance.ready = {}
        with patch('shutil.disk_usage', return_value=SimpleNamespace(free=100*2**30)):
            self.assertFalse(instance.disk_ok()[0])
        with patch('shutil.disk_usage', return_value=SimpleNamespace(free=150*2**30)):
            self.assertTrue(instance.disk_ok()[0])

    def test_outer_deadline_terminates_once_and_records_without_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            instance = Supervisor.__new__(Supervisor)
            instance.root, instance.kind = Path(tmp), 'college'
            instance.ledger = instance.root/'ledger'; instance.ledger.mkdir()
            instance.event = lambda *args, **kwargs: None
            folder = instance.ledger/'hai-task'; folder.mkdir()
            write(folder/'intent.json', {'created': 1, 'hard_deadline_at': 2,
                'task': {'task': 'task', 'agent': {'timeout_sec': 10},
                         'verifier': {'timeout_sec': 10}}, 'method': 'hai'})
            write(folder/'started.json', {'pid': 123, 'identity': 'abc'})
            with patch('supervisor.time.time', return_value=100), \
                 patch('supervisor.identity', return_value='abc'), \
                 patch('supervisor.os.killpg') as kill:
                instance.enforce_deadlines()
                kill.assert_called_once_with(123, signal.SIGTERM)
            with patch('supervisor.time.time', return_value=101), \
                 patch('supervisor.identity', return_value=None):
                instance.enforce_deadlines()
            result = read(folder/'result.json')
            self.assertEqual(result['infrastructure_error'], 'trial_hard_deadline_exceeded')
            self.assertEqual(result['method'], 'hai')


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = self.root/'fixture-key'
        self.key.write_text('fake-offline-credential')
        self.script = Path(__file__).with_name('supervisor.py')
        (self.root/'control.py').write_text('def validate():\n    return {"tasks": ["one", "two"], "disk_reserve_gib": 0.001}\n')
        (self.root/'supervise.py').write_text('''
import json, os, pathlib, sys, time
root=pathlib.Path(__file__).parent
task=sys.argv[2]
d=root/'ledger'/task
fields=pathlib.Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')',1)[1].split()
(d/'started.json').write_text(json.dumps({'pid':os.getpid(),'identity':fields[19]}))
with (root/'launches').open('a') as f: f.write(task+'\\n')
time.sleep(2)
temp=d/'result.tmp'
temp.write_text(json.dumps({'task_id':task, 'needs_attention':task=='one', 'stop_reason':'api_error' if task=='one' else 'model_submit'}))
temp.replace(d/'result.json')
''')
        self.children = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)

    def start(self):
        p = subprocess.Popen([sys.executable, '-B', str(self.script), 'scheduler',
                              str(self.root), 'cube', str(self.key)], stdout=subprocess.DEVNULL)
        self.children.append(p)
        return p

    def wait_for(self, predicate, seconds=40):
        until = time.monotonic()+seconds
        while time.monotonic() < until:
            if predicate(): return
            time.sleep(.1)
        self.fail('timed out waiting for synthetic lifecycle')

    def test_scheduler_restart_reattaches_and_continues_after_failed_trial(self):
        first = self.start()
        self.wait_for(lambda: (self.root/'ledger/one/started.json').exists())
        pid = read(self.root/'ledger/one/started.json')['pid']
        first.terminate(); first.wait(timeout=10)
        second = self.start()
        self.wait_for(lambda: read(self.root/'health.json', {}).get('state') == 'completed_with_errors')
        second.wait(timeout=10)
        self.assertEqual((self.root/'launches').read_text().splitlines(), ['one', 'two'])
        self.assertEqual(read(self.root/'ledger/one/started.json')['pid'], pid)
        self.assertEqual(read(self.root/'health.json')['completed'], 2)
        self.assertEqual(len(read(self.root/'summary-v2.json')), 2)

    def test_missing_child_blocks_without_replay(self):
        folder = self.root/'ledger/one'
        folder.mkdir(parents=True)
        write(folder/'intent.json', {'created': 0, 'task': 'one'})
        worker = self.start()
        self.wait_for(lambda: read(self.root/'health.json', {}).get('state') == 'needs_attention')
        worker.wait(timeout=10)
        self.assertFalse((self.root/'launches').exists())
        self.assertEqual(read(self.root/'health.json')['problems'][0]['reason'], 'child_missing_no_replay')


if __name__ == '__main__':
    unittest.main()
