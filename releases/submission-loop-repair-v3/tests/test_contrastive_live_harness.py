import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'microtests'), str(ROOT/'tests'), str(ROOT/'sources/bestfgs-project/src')]
from run_contrastive import run_pair_member
from test_contrastive_exploration import evidence_action, orthogonal_action, run_action


def reviewed(action, retry=False):
    review = dict(ids=['M1'], observed_result='Two controlled checks failed',
        applicability='Inspect changed fixture dependencies', decision='justified_retry' if retry else 'different_route',
        reason='Explicit mock provider for engineering test, not a real model')
    if retry:
        review['new_evidence'] = 'missing.txt was created by the previous copy operation'
    return dict(memory_review=review, strategy_adjustment='Apply correction and repeat the supplied check', **action)


@unittest.skipUnless(os.name == 'posix', 'requires real Linux bounded CLI')
class ContrastLiveHarnessTests(unittest.TestCase):
    def run_mock(self, arm):
        repair = run_action('microtool','copy','valid.txt','missing.txt',cwd='.')
        check = run_action('microtool','check',cwd='.')
        if arm == 'evidence':
            repair = evidence_action(repair, phase='plan')
            repair['contrastive']['candidates'][1]['action'] = run_action('microtool','read','valid.txt',cwd='.')
            check = evidence_action(check, kind='retry', changed_paths=['missing.txt'])
        else:
            repair, check = orthogonal_action(repair), orthogonal_action(check)
        actions = [reviewed(repair), *([reviewed(check, retry=True)]*(1 if arm == 'evidence' else 3)),
                   reviewed(dict(action='submit', summary='Deliver fixture'))]
        class Mock:
            def __init__(self, config):
                self.config, self.actions, self.request_audit = config, iter(actions), None
            def complete_json(self, **kwargs): return next(self.actions)
            def usage_summary(self): return dict(api_requests=0, api_responses=0)
        with tempfile.TemporaryDirectory() as temp:
            return run_pair_member('path', arm, 'mock-no-api-secret', SimpleNamespace(model='mock-only'),
                Path(temp)/'audit', lambda _:None, transport_factory=Mock)

    def test_evidence_repairs_and_rechecks_with_no_extra_model(self):
        summary = self.run_mock('evidence')
        self.assertTrue(summary['verified_and_submitted'], summary)
        self.assertTrue(summary['public_verification_passed_by_actor'])
        self.assertEqual(summary['agent_tool_calls'], 4)
        self.assertEqual(summary['provider_decisions'], 3)
        self.assertEqual(summary['contrastive_rejections'], 0)
        self.assertEqual(summary['actual_api_usage']['api_requests'], 0)

    def test_orthogonal_rejections_consume_requests_not_tools(self):
        summary = self.run_mock('orthogonal')
        self.assertTrue(summary['fixture_goal_verified'], summary)
        self.assertFalse(summary['submitted'])
        self.assertFalse(summary['public_verification_passed_by_actor'])
        self.assertEqual(summary['contrastive_rejections'], 3)
        self.assertEqual(summary['agent_tool_calls'], 3)
        self.assertEqual(summary['provider_decisions'], 4)
        self.assertEqual(summary['stop_reason'], 'model_or_protocol_error_limit')


if __name__ == '__main__': unittest.main()
