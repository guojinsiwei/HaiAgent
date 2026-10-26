"""Isolated real Linux acceptance: source-only, scripted models, no API access."""
import json
import argparse
import os
from pathlib import Path
import platform
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/bestfgs-project/tests'), str(ROOT/'tests')]
from bestfgs.command_io import snapshot_logs, recover_logs
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import OpenAICompatibleJSONClient
from bestfgs.terminal_text import clean_terminal
from bestfgs.tool_outcomes import assess
from test_lean import Scripted, run_action, SUBMIT


class LinuxPreflight(unittest.TestCase):
    def setUp(self):
        self.assertEqual(os.name,'posix','This acceptance must run on Linux')
        self.tmp = tempfile.TemporaryDirectory(prefix='linux-preflight-',dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        seed = self.root/'seed'; seed.mkdir()
        self.env = LiveWorkspace(seed,self.root/'run')

    def execute(self, action):
        return self.env.execute(action,time.monotonic()+10)

    def test_dev_null_clean_read_write(self):
        code = ('import os,stat; assert stat.S_ISCHR(os.stat("/dev/null").st_mode); '
                'f=os.open("/dev/null",os.O_RDWR); assert os.write(f,b"probe")==5; '
                'assert os.read(f,1)==b""; os.close(f); print("device-ok")')
        result = self.execute(run_action(sys.executable,'-c',code))
        self.assertEqual(result.return_code,0)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.stdout.strip(),'device-ok')
        self.assertEqual(result.stderr,'')

    def test_real_pipeline_failure_is_not_clean_success(self):
        self.env.outcome_reliability = True
        result = self.execute(run_action('bash','-lc','false | true'))
        self.assertEqual(result.return_code,0)  # Preserve the shell's semantics.
        self.assertEqual(result.stderr,'')
        self.assertTrue(result.execution_observation['complete'])
        self.assertTrue(result.execution_observation['nonzero_statuses'])
        assessment = assess(result)
        self.assertTrue(assessment['process_succeeded'])
        self.assertFalse(assessment['execution_clean'])
        self.assertIsNone(assessment['task_success'])

    def test_log_recovery_cannot_follow_symlink_outside_workspace(self):
        outside = self.root/'outside'; outside.mkdir()
        path = outside/'qout.txt'; path.write_text('out-of-workspace fixture')
        (self.env.workspace/'logs').symlink_to(outside,target_is_directory=True)
        action = run_action('bash','-lc','make qemu > logs/qout.txt')
        before = snapshot_logs(action,workspace_root=self.env.workspace)
        self.assertEqual(recover_logs(action,before=before,workspace_root=self.env.workspace),[])
        self.assertEqual(path.read_text(),'out-of-workspace fixture')

    def test_real_terminal_output_is_cleaned_without_discarding_raw_evidence(self):
        result = self.execute(run_action(sys.executable,'-c',
                                        'print("\\x1b[31mfixture-error\\x1b[0m")'))
        self.assertEqual(result.return_code,0)
        self.assertIn('\x1b[31m',result.stdout)
        self.assertEqual(clean_terminal(result.stdout).strip(),'fixture-error')

    def test_expectation_closed_loop_with_real_file_and_no_extra_request(self):
        action = run_action(sys.executable,'-c',
            'from pathlib import Path; Path("output.txt").write_text("fixture-result")',
            expected_observation=dict(kind='file_state',path='output.txt',state='file',changed=True))
        actor = Scripted([action,SUBMIT])
        config = LeanConfig(max_turns=2,max_tools=1,command_seconds=10,
                            memory_reliability=True,outcome_reliability=True,
                            contrastive_mode='orthogonal',contrastive_predictions=False)
        result = LeanTaskRunner(self.env,actor,Scripted([]),config,self.root/'audit').run(
            TaskSpec('offline-linux-fixture','Create output.txt'))
        self.assertTrue(result['submitted'],result)
        self.assertEqual(result['version'],'DHv1')
        self.assertEqual(result['tool_calls'],1)
        self.assertEqual(result['interaction_rounds'],2)
        self.assertEqual(result['mechanism_utilization']['expectations_matched'],1)
        self.assertEqual((self.env.workspace/'output.txt').read_text(),'fixture-result')
        evidence = actor.prompts[1]['fixed_context']['evidence']
        self.assertEqual(evidence[-1]['expectation']['status'],'matched')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report-name',default='linux-acceptance-summary.json')
    args = parser.parse_args()
    if Path(args.report_name).name != args.report_name or not args.report_name.endswith('.json'):
        parser.error('report-name must be a plain JSON filename')
    if os.name != 'posix':
        raise SystemExit('Linux acceptance requires a POSIX host')
    loader = unittest.TestLoader()
    suite = unittest.TestSuite(loader.discover(str(ROOT/'tests'),pattern=name)
        for name in ('test_core_lean.py','test_engineering_fixes.py','test_expectation.py',
                     'test_boundary_engineering.py','test_transport_wire.py'))
    suite.addTests(loader.loadTestsFromTestCase(LinuxPreflight))
    attempts = dict(network=0,model_api=0)
    def deny_network(*args,**kwargs):
        attempts['network'] += 1
        raise AssertionError('Network access forbidden in offline acceptance')
    def deny_model(*args,**kwargs):
        attempts['model_api'] += 1
        raise AssertionError('Real model access forbidden in offline acceptance')
    started = time.monotonic()
    with patch.object(socket.socket,'connect',deny_network), \
         patch.object(socket.socket,'connect_ex',deny_network), \
         patch.object(socket,'create_connection',deny_network), \
         patch.object(OpenAICompatibleJSONClient,'_request_bytes',deny_model):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(release='DHv1',platform=platform.platform(),python=platform.python_version(),
        tests_run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        failures=[case.id() for case,_ in result.failures],errors=[case.id() for case,_ in result.errors],
        skipped=[dict(test=case.id(),reason=reason) for case,reason in result.skipped],
        duration_seconds=round(time.monotonic()-started,3),blocked_access_attempts=attempts,
        passed_acceptance=result.wasSuccessful() and not result.skipped and not any(attempts.values()),
        scope='Isolated LiveWorkspace, not existing Cube workers or real QEMU guest/grading',
        paid_api_calls=0)
    (ROOT/args.report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return int(not report['passed_acceptance'])


if __name__ == '__main__':
    raise SystemExit(main())
