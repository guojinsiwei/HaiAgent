"""Integration of raw evidence, conditional suggestions and the active view."""
from dataclasses import asdict, replace
import json
import unittest

import test_experience as fixtures
from bestfgs.models import CommandResult, ConditionalExperience, ExperiencePremise
from bestfgs.retrac_adapter import _project_rules_for_prompt


class MicroExperienceStoreTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.TaskExperienceTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.store = self.fx.store

    def lesson(self, *, index=0, premises=None):
        return ConditionalExperience(
            operation="normalize_input", target_paths=("module.py",),
            premises=premises or (ExperiencePremise("input", "equals", "None"),),
            source_channel="command", source_index=index,
            lesson="The observed None input failed; the proposed causal explanation remains unverified.",
            next_check="Check None and non-empty strings after repairing the input guard.",
        )

    def observe_failure(self, hint=None):
        action = self.fx.action(self.fx.query())
        output = CommandResult(action.commands[0], 1, "", "AttributeError: None input", 0)
        transition = self.fx.transition(action, results=(output,), feedback="Observed failure only")
        transition = replace(transition, assessment=replace(
            transition.assessment, micro_experiences=(hint or self.lesson(),)))
        self.store.observe(transition)
        return transition

    def proposal(self, value="None"):
        return replace(self.fx.action(self.fx.query()), experience_operation="normalize_input",
                       experience_targets=("module.py",),
                       experience_premises=(ExperiencePremise("input", "equals", value),))

    def test_duplicate_observations_keep_all_sources_but_one_active_entry(self):
        action = self.fx.action(self.fx.query())
        for _ in range(20):
            self.store.observe(self.fx.transition(action, feedback=""))
        entries = self.store.report()["micro_experiences"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(len(entries[0]["source_ids"]), 20)
        rules = self.store.retrieve(context=self.fx.context, snapshot=self.fx.snapshot(), limit=5)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].source_count, 20)
        self.assertLessEqual(len(rules[0].evidence_ids), 3)
        self.assertTrue(_project_rules_for_prompt(rules))
        self.assertFalse(self.store.report()["micro_index"]["repetition_is_independent_confidence"])

    def test_source_is_this_transition_and_replay_is_idempotent(self):
        transition = self.observe_failure()
        before = self.store.report()
        self.assertEqual(self.store.observe(transition), ())
        self.assertEqual(before, self.store.report())
        entry = next(x for x in before["micro_experiences"] if x["kind"] == "conditional_hypothesis")
        observation = next(x for x in self.store.all() if x.kind == "observation")
        self.assertEqual(entry["source_ids"], (observation.evidence_id,))
        self.assertEqual(observation.source_index, 0)
        self.assertEqual(entry["causal_status"], "not_established")

    def test_invalid_source_does_not_poison_real_observations(self):
        self.observe_failure(self.lesson(index=99))
        self.assertTrue(self.store.all())
        self.assertFalse(any(x["kind"] == "conditional_hypothesis"
                             for x in self.store.report()["micro_experiences"]))
        self.assertEqual(self.store.report()["micro_lessons_invalid_source"], 1)

    def test_declared_premise_match_is_not_a_hard_veto(self):
        self.observe_failure()
        decision = self.store.evaluate(action=self.proposal(), snapshot=self.fx.snapshot())
        match = next(x for x in decision.micro_matches if x["kind"] == "conditional_hypothesis")
        self.assertEqual(match["condition_status"], "declared_match")
        self.assertIn("explicit_operation_match", match["match_reasons"])
        self.assertFalse(match["hard_block_eligible"])
        self.assertFalse(decision.blocked)
        self.assertIn("advisory only", " ".join(decision.feedback))
        json.dumps(asdict(decision))

    def test_changed_premise_allows_retry_not_automatic_success(self):
        self.observe_failure()
        decision = self.store.evaluate(action=self.proposal("str"), snapshot=self.fx.snapshot())
        match = next(x for x in decision.micro_matches if x["kind"] == "conditional_hypothesis")
        self.assertEqual(match["condition_status"], "declared_changed")
        self.assertFalse(decision.blocked)
        self.assertIn("verify", match["advice"])
        self.assertEqual(match["causal_status"], "not_established")

    def test_file_premise_rechecked_in_current_branch(self):
        self.observe_failure(self.lesson(premises=(ExperiencePremise("module.py", "file_contains", "value = 1"),)))
        proposal = self.proposal()
        old = self.store.evaluate(action=proposal, snapshot=self.fx.snapshot())
        match = next(x for x in old.micro_matches if x["kind"] == "conditional_hypothesis")
        self.assertEqual(match["premises"][0]["status"], "valid")
        branch = self.fx.branch("different", {"module.py": "value = 9\n"})
        new = self.store.evaluate(action=proposal, snapshot=branch)
        match = next(x for x in new.micro_matches if x["kind"] == "conditional_hypothesis")
        self.assertEqual(match["premises"][0]["status"], "changed")
        self.assertFalse(new.blocked)

    def test_planning_view_exposes_full_condition_and_trace_not_confidence(self):
        self.observe_failure()
        rules = self.store.retrieve(context=self.fx.context, snapshot=self.fx.snapshot(), limit=5)
        rule = next(x for x in rules if x.experience_kind == "conditional_hypothesis")
        self.assertEqual(rule.operation, "normalize_input")
        self.assertEqual(rule.premises[0]["value"], "None")
        self.assertTrue(rule.evidence_ids)
        payload = _project_rules_for_prompt((rule,))
        self.assertTrue(payload)
        self.assertEqual(payload[0]["premises"][0]["value"], "None")
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))), 2500)
        self.assertIsNone(self.store.report()["false_block_rate"])


if __name__ == "__main__":
    unittest.main()
