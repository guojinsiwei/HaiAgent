import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'sources/bestfgs-project/src'), str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.contrastive_exploration import (command_text, tfidf_similarity,
    validate_evidence, validate_orthogonal)
from bestfgs.lean_memory import action_key
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec
from test_lean import Scripted, FakeEnvironment, run_action, SUBMIT


def anchor(action, **extra):
    return dict(id='F1', command=command_text(action), command_key=action_key(action),
                scope='old', dependencies={'config.json': 'file:old'}, **extra)


def candidate(action, **extra):
    return dict(id='A', anchor_ids=['F1'], hypothesis='The configuration is wrong',
        difference='Check one changed lever', kind='probe', action=action,
        supports='OK', refutes='ERROR', changed_paths=[], evidence_ids=[], **extra)


def evidence_action(action, phase='followup', **extra):
    chosen = candidate(action)
    chosen.update(extra)
    rows = [chosen]
    if phase == 'plan':
        other = candidate(run_action('inspect', 'config.json'))
        other.update(id='B', hypothesis='The input file is wrong')
        rows.append(other)
    return dict(action, contrastive=dict(selected='A', candidates=rows))


def orthogonal_action(action):
    return dict(action, contrastive=dict(negative_anchors_summary='A recorded failure',
        proposed_strategy='Claim a different route', orthogonality_proof=dict(
            dependency_dimension='Claim changed dependency', target_dimension='Claim changed target',
            command_dimension='Claim changed type'), final_command=command_text(action)))


def check_evidence(action, anchors, deps=None, phase='followup', retries=None):
    return validate_evidence(action, anchors, 'new', deps or {'config.json': 'file:old'},
                             {'E1', 'E2'}, phase, retries or set())


class ContrastPolicyTests(unittest.TestCase):
    def test_word_tfidf_matches_default_formula(self):
        scores = tfidf_similarity('alpha beta', ['alpha beta', 'gamma delta'])
        self.assertAlmostEqual(scores['per_anchor'][0], 1)
        self.assertAlmostEqual(scores['per_anchor'][1], 0)
        self.assertAlmostEqual(tfidf_similarity('alpha beta', ['alpha'])['max_similarity'],
            1 / (1 + (1 + __import__('math').log(3/2))**2)**.5)

    def test_empty_vocabulary_is_explicit_not_format_error(self):
        self.assertTrue(tfidf_similarity('a 1', ['b 2'])['empty_vocabulary'])

    def test_actual_changed_numeric_parameter_allowed_by_both_policies(self):
        old = run_action('python', 'train.py', '--batch', '2')
        new = run_action('python', 'train.py', '--batch', '1')
        anchors = [anchor(old)]
        self.assertIsNone(check_evidence(evidence_action(new), anchors)[1])
        audit, rejection = validate_orthogonal(orthogonal_action(new), anchors, .8)
        self.assertIsNone(rejection)
        self.assertTrue(audit['similarity_warning'])
        self.assertAlmostEqual(audit['max_similarity'], 1)

    def test_repaired_related_file_allows_same_check_only_evidence(self):
        check = run_action('python', 'check.py', 'config.json')
        anchors = [anchor(check)]
        action = evidence_action(check, kind='retry', changed_paths=['config.json'])
        audit, rejection = check_evidence(action, anchors, {'config.json': 'file:new'})
        self.assertIsNone(rejection)
        self.assertEqual(audit['exemptions'][0]['reason'], 'observed_relevant_file_change')
        self.assertIsNone(validate_orthogonal(orthogonal_action(check), anchors, .8)[1])

    def test_irrelevant_file_and_invented_changed_path_do_not_clear_failure(self):
        check = run_action('python', 'check.py', 'config.json')
        for paths, deps in [(['notes.txt'], {'config.json': 'file:old', 'notes.txt': 'file:new'}),
                            (['config.json'], {'config.json': 'file:old'})]:
            action = evidence_action(check, kind='retry', changed_paths=paths)
            self.assertIsNotNone(check_evidence(action, [anchor(check)], deps)[1])

    def test_shell_spacing_and_argument_quotes_cannot_bypass_evidence(self):
        old = run_action('bash', '-lc', 'python check.py config.json')
        new = run_action('bash', '-lc', ' python  "check.py"  config.json ')
        self.assertIsNotNone(check_evidence(evidence_action(new), [anchor(old)])[1])
        self.assertIsNone(validate_orthogonal(orthogonal_action(new), [anchor(old)], .8)[1])

    def test_new_diagnostic_admitted_by_both(self):
        old = run_action('python', 'check.py', 'config.json')
        new = run_action('cat', 'environment.txt')
        self.assertIsNone(check_evidence(evidence_action(new), [anchor(old)])[1])
        self.assertIsNone(validate_orthogonal(orthogonal_action(new), [anchor(old)], .8)[1])

    def test_claimed_dimensions_are_not_verified_by_tfidf(self):
        action = orthogonal_action(run_action('cat', 'environment.txt'))
        audit, rejection = validate_orthogonal(action, [anchor(run_action('pip', 'install', 'foo'))], .8)
        self.assertIsNone(rejection)
        self.assertFalse(audit['dimension_claims_verified'])

    def test_proof_command_must_match_executed_command(self):
        action = orthogonal_action(run_action('python', 'check.py'))
        action['contrastive']['final_command'] = 'cat environment.txt'
        with self.assertRaises(ValueError): validate_orthogonal(action, [], .8)

    def test_missing_dimension_is_refused(self):
        action = orthogonal_action(run_action('cat', 'environment.txt'))
        del action['contrastive']['orthogonality_proof']['target_dimension']
        with self.assertRaises(ValueError): validate_orthogonal(action, [], .8)

    def test_unavailable_anchor_evidence_and_candidate_mismatch_refused(self):
        action = evidence_action(run_action('cat', 'environment.txt'))
        for key, value in [('anchor_ids', ['F99']), ('evidence_ids', ['E99']),
                           ('action', run_action('python', 'check.py'))]:
            bad = copy.deepcopy(action); bad['contrastive']['candidates'][0][key] = value
            with self.assertRaises(ValueError): check_evidence(bad, [anchor(run_action('pip', 'install', 'foo'))])

    def test_external_retry_is_bounded_and_audited_as_unverified(self):
        old = run_action('python', 'check.py', 'config.json')
        action = evidence_action(old, kind='retry', external_recheck=True)
        audit, rejection = check_evidence(action, [anchor(old)])
        self.assertIsNone(rejection)
        self.assertEqual(audit['exemptions'][0]['reason'], 'one_external_recheck_unverified')
        self.assertIsNotNone(check_evidence(action, [anchor(old)], retries=set(audit['retry_signatures']))[1])

    def test_plan_needs_two_followup_needs_one(self):
        action = evidence_action(run_action('cat', 'environment.txt'), phase='plan')
        self.assertIsNone(check_evidence(action, [anchor(run_action('pip', 'install', 'foo'))], phase='plan')[1])
        with self.assertRaises(ValueError): check_evidence(action, [], phase='followup')

    def test_no_hai_configuration_allowed(self):
        with self.assertRaises(ValueError): LeanConfig(contrastive_mode='evidence', stagnation_control=True)
        with self.assertRaises(ValueError): LeanConfig(contrastive_mode='orthogonal', contrastive_threshold=1)


class RuntimeIntegrationTests(unittest.TestCase):
    def exercise(self, mode):
        actions = [run_action('fail'), run_action('fail')]
        next_action = run_action('write', 'fixed')
        if mode == 'evidence':
            action = evidence_action(next_action, phase='plan')
        else:
            action = orthogonal_action(next_action)
            action['contrastive'].update(selected='A', candidates=[
                dict(id='A',hypothesis='Repair the public input', action=next_action,
                     supports='fixed',refutes='same error'),
                dict(id='B',hypothesis='Inspect another input',action=run_action('inspect','other.txt'),
                     supports='OTHER',refutes='missing')])
        # M1 is the original v8 observed failure memory, F1/F2 exploration anchors.
        action = dict(memory_review=dict(ids=['M1'], observed_result='Two failures',
            applicability='Historical', decision='different_route', reason='Try correction'),
            strategy_adjustment='Modify and validate', **action)
        submit = dict(memory_review=dict(ids=['M1'], observed_result='Two historical failures',
            applicability='Changed', decision='not_applicable', reason='Deliver current result'),
            strategy_adjustment='Deliver corrected artifact', **SUBMIT)
        actions += [action, submit]
        with tempfile.TemporaryDirectory() as temp:
            actor = Scripted(actions)
            runner = LeanTaskRunner(FakeEnvironment(), actor, Scripted([]),
                LeanConfig(contrastive_mode=mode, auto_memory=True, memory_reliability=True,
                    outcome_reliability=True, max_turns=12, max_tools=8, max_advisor_calls=0),
                Path(temp)/'audit', monitor_client=Scripted([]))
            result = runner.run(TaskSpec('contrast', 'Fix config parser'))
            return result, actor.prompts, read_trace(Path(temp)/'audit/events.jsonl')

    def test_both_policies_reach_actual_request_and_execute_selected_action_once(self):
        for mode in ('evidence', 'orthogonal'):
            with self.subTest(mode=mode):
                result, prompts, events = self.exercise(mode)
                self.assertTrue(result['submitted'], result)
                self.assertEqual(result['tool_calls'], 2)  # cached unchanged failure is not re-executed
                self.assertEqual(result['interaction_rounds'], 4)
                self.assertTrue(prompts[2]['fixed_context']['contrastive_exploration']['active'])
                self.assertTrue(any(e['event'] == 'contrastive_outcome' for e in events))
                self.assertFalse(result['mechanism_utilization'].get('branch_restores'))


if __name__ == '__main__': unittest.main()
