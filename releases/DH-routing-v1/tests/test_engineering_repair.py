import copy
import json
from pathlib import Path
import shlex
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.memory_injection import (REVIEW_LIMITS, ReviewValidationError,
    review_repair_feedback, validate_review, MEMORY_INSTRUCTION)
from bestfgs.contrastive_exploration import validate_orthogonal
import test_memory_injection as memory_tests
from test_memory_injection import review
from test_contrastive_exploration import orthogonal_action, anchor
from test_lean import run_action, SUBMIT


class ReviewRepairTests(unittest.TestCase):
    def test_existing_limits_not_relaxed_and_prompt_advertises_them(self):
        self.assertEqual(REVIEW_LIMITS, dict(reason=400, observed_result=400,
            applicability=300, strategy_adjustment=400, new_evidence=300))
        self.assertIn('1..300', MEMORY_INSTRUCTION)
        self.assertIn('1..400', MEMORY_INSTRUCTION)

    def test_all_text_fields_have_exact_boundary_and_precise_overflow(self):
        for field, limit in REVIEW_LIMITS.items():
            with self.subTest(field=field):
                value = review(SUBMIT, 'justified_retry')
                value['memory_review']['new_evidence'] = 'Changed source; compare tests.'
                target = value if field == 'strategy_adjustment' else value['memory_review']
                target[field] = 'x' * limit
                validate_review(value, {'M1'}, True)
                target[field] += 'x'
                with self.assertRaises(ReviewValidationError) as caught:
                    validate_review(value, {'M1'}, True)
                feedback = review_repair_feedback(caught.exception)
                self.assertEqual(feedback['actual_chars'], limit + 1)
                self.assertEqual(feedback['max_chars'], limit)
                self.assertEqual(feedback['error_code'], 'memory_review_too_long')
                self.assertNotIn('must state a concrete', str(caught.exception))

    def test_missing_empty_wrong_type_nul_are_not_length_errors(self):
        for value, code in [(None, 'wrong_type'), ({}, 'wrong_type'),
                            ('  ', 'empty'), ('a\x00b', 'nul_character')]:
            with self.subTest(value=value):
                action = review(SUBMIT)
                action['strategy_adjustment'] = value
                with self.assertRaises(ReviewValidationError) as caught:
                    validate_review(action, {'M1'}, True)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.field, 'strategy_adjustment')

    def test_error_feedback_does_not_echo_untrusted_field_text(self):
        action = review(SUBMIT)
        action['strategy_adjustment'] = 'untrusted-instruction-' * 40
        with self.assertRaises(ReviewValidationError) as caught:
            validate_review(action, {'M1'}, True)
        self.assertNotIn('untrusted-instruction', json.dumps(review_repair_feedback(caught.exception)))
        self.assertIsNone(review_repair_feedback(ValueError('not a field format error')))

    def test_real_spot_scheduler_overflow_is_diagnosed_as_length_not_quality(self):
        # Exact recorded last adjustment in orthogonal1 spot-scheduler trial.
        value = ('Stop trusting the local score as ground truth. Inspect the harness source to learn '
                 'how SchedulerPolicy is instantiated, what action strings are compared, and how '
                 'scoring is computed. Verification: if the harness contract (constructor args, '
                 'action casing, trace generator) differs from what policy.py assumes, that explains '
                 'the grader failure; if it matches exactly, the failure lies elsewhere and I will '
                 "re-examine the policy's edge-case behavior.")
        self.assertGreater(len(value), 400)
        action = review(SUBMIT)
        action['strategy_adjustment'] = value
        with self.assertRaises(ReviewValidationError) as caught:
            validate_review(action, {'M1'}, True)
        self.assertEqual(caught.exception.code, 'too_long')
        corrected = copy.deepcopy(action)
        corrected['strategy_adjustment'] = ('Inspect the public harness and policy.py interface; '
            'compare constructor arguments and return values, then test any mismatch.')
        self.assertIsNotNone(validate_review(corrected, {'M1'}, True))
        self.assertEqual(action['strategy_adjustment'], value)  # no silent truncation

    def test_unknown_memory_ids_still_rejected(self):
        action = review(SUBMIT)
        action['memory_review']['ids'] = ['M99']
        with self.assertRaisesRegex(ValueError, 'current visible'):
            validate_review(action, {'M1'}, True)


class RuntimeRepairTests(unittest.TestCase):
    exercise = memory_tests.InjectionTests.exercise
    def test_exact_feedback_reaches_next_request_and_bad_command_is_not_executed(self):
        bad = review(run_action('write', 'NOT_ALLOWED'))
        bad['strategy_adjustment'] = 'x' * 401
        result, runner, actor, events = self.exercise([run_action('fail'), run_action('fail'),
            bad, review(run_action('write', 'fixed')), review(SUBMIT)])
        self.assertTrue(result['submitted'], result)
        self.assertEqual(result['tool_calls'], 3)
        self.assertNotIn('NOT_ALLOWED', [a['argv'][-1] for a in runner.environment.executed])
        error = next(e for e in events if e['event'] == 'protocol_error')
        self.assertEqual(error['field'], 'strategy_adjustment')
        self.assertEqual(error['actual_chars'], 401)
        self.assertIn('memory_review_too_long', actor.calls[3]['user_prompt'])
        self.assertIn('Do not change route', actor.calls[3]['user_prompt'])
        panel = json.loads(actor.calls[3]['user_prompt'])['fixed_context']
        self.assertEqual(panel['memory_action_contract']['field_max_chars'], REVIEW_LIMITS)

    def test_repeated_format_failure_remains_bounded_without_hidden_retries(self):
        bad = review(run_action('write', 'NOT_ALLOWED'))
        bad['strategy_adjustment'] = 'x' * 401
        result, runner, actor, events = self.exercise([run_action('fail'), run_action('fail'), bad, bad, bad])
        self.assertEqual(result['stop_reason'], 'model_or_protocol_error_limit')
        self.assertEqual(result['interaction_rounds'], 5)
        self.assertEqual(result['tool_calls'], 2)


class ShellProofRepairTests(unittest.TestCase):
    def test_exact_body_and_full_wrapper_are_consistent_and_same_similarity(self):
        argv = ['bash', '-lc', 'python check.py --value 2']
        action = orthogonal_action(run_action(*argv))
        anchors = [anchor(run_action('python', 'check.py', '--value', '2'))]
        body = validate_orthogonal(action, anchors, .8)
        action['contrastive']['final_command'] = shlex.join(argv)
        wrapper = validate_orthogonal(action, anchors, .8)
        self.assertEqual(body, wrapper)
        self.assertEqual(wrapper[1], 'command_similarity_above_threshold')

    def test_different_script_quoting_whitespace_and_extra_command_still_rejected(self):
        action = orthogonal_action(run_action('bash', '-lc', 'echo "a b"'))
        for proof in ['echo a b', 'echo  "a b"', 'echo "a b"; touch evil',
                      shlex.join(['bash', '-lc', 'echo a b']), 'bash -c \'echo "a b"\'']:
            with self.subTest(proof=proof):
                action['contrastive']['final_command'] = proof
                with self.assertRaises(ValueError): validate_orthogonal(action, [], .8)


if __name__ == '__main__':
    unittest.main()
