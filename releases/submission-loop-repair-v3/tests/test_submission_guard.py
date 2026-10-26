import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_audit import read_trace, digest
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec
from bestfgs.submission_guard import SubmissionGuard
from test_lean import FakeEnvironment, Scripted, run_action, SUBMIT


def revision(eid='E2', sid='S1'):
    return dict(SUBMIT, submission_revision=dict(rejection_id=sid,
        hypothesis='Current output violates the public schema',
        change='Correct the output schema', validation_evidence_ids=[eid]))


class SubmissionTests(unittest.TestCase):
    def exercise(self, actions, feedback=None, env=None, **config):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        env = env or FakeEnvironment()
        actor = Scripted(actions)
        runner = LeanTaskRunner(env, actor, Scripted([]),
            LeanConfig(max_turns=40, max_tools=30, **config),
            Path(tmp.name)/'audit', submission_feedback=feedback)
        result = runner.run(TaskSpec('fixture', 'Create useful output'))
        return result, read_trace(Path(tmp.name)/'audit/events.jsonl'), env, actor

    def test_first_submission_is_unrestricted_and_never_claims_success(self):
        result, _, env, _ = self.exercise([SUBMIT])
        self.assertTrue(result['submitted'])
        self.assertIsNone(result['official_success'])
        self.assertEqual(env.deliveries, 1)

    def test_320_repeated_submissions_make_one_feedback_call_then_stop(self):
        calls = []
        result, rows, env, actor = self.exercise([SUBMIT]*320,
            feedback=lambda a: calls.append(a) or 'rejected')
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['stop_reason'], 'submission_stagnation')
        self.assertEqual(result['mechanism_utilization']['submission_blocks'], 3)
        self.assertEqual(result['interaction_rounds'], 4)
        self.assertFalse(result['submitted'])
        self.assertEqual(env.deliveries, 2)  # attempted delivery + final preservation
        self.assertEqual(actor.prompts[1]['fixed_context']['submission_guard']['last_rejection']['id'], 'S1')
        self.assertEqual(sum(r['event']=='submission_blocked' for r in rows), 3)

    def test_summary_whitespace_and_claimed_strategy_change_do_not_unlock(self):
        actions = [SUBMIT] + [dict(revision(), summary='new words ' + ' '*i) for i in range(3)]
        result, rows, _, _ = self.exercise(actions, feedback=lambda _: 'rejected')
        self.assertEqual(result['mechanism_utilization']['submissions'], 1)
        self.assertTrue(all(r['error_code']=='unchanged_or_previously_rejected_workspace'
                            for r in rows if r['event']=='submission_blocked'))

    def test_real_repair_then_fresh_complete_check_can_resubmit(self):
        outcomes = iter(['rejected', None])
        result, rows, _, _ = self.exercise([SUBMIT, run_action('write','fixed'),
            run_action('verify'), revision()], feedback=lambda _: next(outcomes))
        self.assertTrue(result['submitted'])
        self.assertEqual(result['mechanism_utilization']['submissions'], 2)
        self.assertEqual(result['mechanism_utilization']['resubmissions_with_new_evidence'], 1)
        check = next(r for r in rows if r['event']=='submission_revision_checked')
        self.assertFalse(check['causal_hypothesis_verified'])

    def test_new_check_does_not_unlock_unchanged_files(self):
        actions = [SUBMIT]
        for i in range(1,4):
            actions.extend([run_action('verify'), revision('E'+str(i))])
        result, _, _, _ = self.exercise(actions, feedback=lambda _: 'rejected')
        self.assertEqual(result['stop_reason'], 'submission_stagnation')
        self.assertEqual(result['mechanism_utilization']['submissions'], 1)

    def test_restoring_an_earlier_rejected_state_is_not_a_new_candidate(self):
        actions = [SUBMIT, run_action('write','fixed'), run_action('verify'), revision(),
                   run_action('write','seed'), run_action('verify')] + [revision('E4','S2')]*3
        result, _, _, _ = self.exercise(actions, feedback=lambda _: 'rejected')
        self.assertEqual(result['mechanism_utilization']['submissions'], 2)
        self.assertEqual(result['stop_reason'], 'submission_stagnation')

    def test_failed_or_stale_or_read_only_listing_is_not_validation(self):
        for action in [run_action('fail'), run_action('ls'), run_action('echo','passed')]:
            with self.subTest(argv=action['argv']):
                actions = [SUBMIT, run_action('write','fixed'), action] + [revision()]*3
                result, _, _, _ = self.exercise(actions, feedback=lambda _: 'rejected')
                self.assertEqual(result['mechanism_utilization']['submissions'], 1)
        actions = [SUBMIT, run_action('write','fixed'), run_action('verify'),
                   run_action('write','changed-after-check')] + [revision()]*3
        result, _, _, _ = self.exercise(actions, feedback=lambda _: 'rejected')
        self.assertEqual(result['mechanism_utilization']['submissions'], 1)

    def test_cosmetic_distinct_revisions_still_have_a_fixed_rejection_cap(self):
        actions = [SUBMIT]
        for i in range(1,12):
            actions.extend([run_action('write','cosmetic-'+str(i)), run_action('verify'),
                            revision('E'+str(2*i), 'S'+str(i))])
        result, _, _, _ = self.exercise(actions, feedback=lambda _: 'rejected')
        self.assertEqual(result['mechanism_utilization']['submissions'], 8)
        self.assertEqual(result['stop_reason'], 'submission_stagnation')
        self.assertEqual(result['artifact']['value'], 'cosmetic-7')

    def test_explicit_contract_blocks_unrelated_workspace_edit(self):
        env = FakeEnvironment(); env.dependencies['output.json'] = 'file:same'
        actions = [SUBMIT, run_action('write','unrelated'), run_action('verify')] + [revision()]*3
        result, rows, _, _ = self.exercise(actions, feedback=lambda _: 'rejected', env=env,
                                          submission_artifact_paths=('output.json',))
        self.assertEqual(result['mechanism_utilization']['submissions'], 1)
        self.assertIn('unchanged_or_previously_rejected_public_artifacts',
                      [r.get('error_code') for r in rows])

    def test_explicit_contract_with_real_output_change_is_allowed(self):
        outcomes = iter(['rejected', None])
        result, _, _, _ = self.exercise([SUBMIT, run_action('artifact','output.json','fixed'),
            run_action('verify'), revision()], feedback=lambda _: next(outcomes),
            submission_artifact_paths=('output.json',))
        self.assertTrue(result['submitted'])

    def test_read_only_actions_do_not_reset_block_limit(self):
        actions = [SUBMIT]
        for _ in range(3):
            actions.extend([SUBMIT, run_action('read')])
        result, _, _, _ = self.exercise(actions, feedback=lambda _: 'rejected')
        self.assertEqual(result['stop_reason'], 'submission_stagnation')
        self.assertEqual(result['mechanism_utilization']['submission_blocks'], 3)

    def test_config_refuses_private_or_unsafe_contract_paths_and_invalid_caps(self):
        for paths in [('tests/hidden.py',), ('../escape.json',), ('/app/a.json',), ['a.json']]:
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                LeanConfig(submission_artifact_paths=paths)
        for kwargs in [dict(max_submission_blocks=0),dict(max_rejected_submissions=0),dict(submission_guard=1)]:
            with self.assertRaises(ValueError): LeanConfig(**kwargs)

    def test_stagnation_is_recorded_as_method_failure_not_infrastructure_success(self):
        from importlib.util import spec_from_file_location, module_from_spec
        spec = spec_from_file_location('submission_outcomes', ROOT/'integration/outcomes.py')
        module = module_from_spec(spec); spec.loader.exec_module(module)
        classification = module.classify(dict(process_exit_code=0, verifier_result={'rewards':{'reward':0.5}}),
            [dict(event='method_end',result=dict(stop_reason='submission_stagnation'))])
        self.assertTrue(classification['infrastructure_ok'])
        self.assertEqual(classification['method_issues'], ['submission_stagnation'])


if __name__ == '__main__':
    unittest.main()
