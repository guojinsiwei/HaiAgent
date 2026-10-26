"""Real forked-workspace, scripted-policy tests of *used* micro experience.

These are controlled implementation counterexamples, not benchmark effectiveness
or measured causal savings. There are no API calls, hidden tests or gold patches.
"""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_experience_runtime import ReadFixtureEnvironment, cat, check, macro, write_value
from bestfgs.agent import TaskRunner
from bestfgs.best_first import SemanticBestFirstGraphSearch
from bestfgs.best_first_runtime import BestFGSConfig
from bestfgs.models import (
    ConditionalExperience, ExperiencePremise, InitialSemanticPlan, SearchGraph,
    SemanticDirection, StructuredContext, TaskSpec, TransitionAssessment, TransitionUpdate,
)
from bestfgs.rules import TaskRuleStore
from bestfgs.semantic import project_context_for_prompt


OPERATION = "repair_public_zero_value"
LESSON = "PUBLIC_ZERO_COUNTEREXAMPLE: value zero failed the public check; choose value one, not two."
NEXT_CHECK = "Rerun check.py on this candidate; never inherit an old PASS."


class MicroGuidedPolicy:
    """Only the indexed, condition-bearing lesson changes the planned repair."""

    def __init__(self, *, unconditional_repair=False, unknown_premise=False):
        self.unconditional_repair = unconditional_repair
        self.unknown_premise = unknown_premise
        self.planning_calls = 0
        self.update_calls = 0
        self.executed = []
        self.seen_contexts = []
        self.seen_rules = []
        self.guiding_rules = []

    def premises(self):
        if self.unknown_premise:
            return (ExperiencePremise("semantic_intent", "equals", "public_zero_behavior"),)
        return (ExperiencePremise("value.txt", "file_contains", "0"),)

    def remember_prompt(self, kwargs):
        self.planning_calls += 1
        self.seen_contexts.append(kwargs["context"])
        self.seen_rules.append(kwargs["rules"])

    def propose_initial_plan(self, **kwargs):
        self.remember_prompt(kwargs)
        return InitialSemanticPlan((SemanticDirection("repair", "repair value public zero counterexample"),),
            macro("prefix", [cat()], checks=[check()], candidate=True))

    def propose_actions(self, **kwargs):
        self.remember_prompt(kwargs)
        stage = kwargs["context"].current_solution
        if stage == "prefix":
            lessons = [rule for rule in kwargs["rules"]
                       if rule.micro_experience_id and rule.operation == OPERATION
                       and "PUBLIC_ZERO_COUNTEREXAMPLE" in rule.guidance
                       and rule.target_paths == ("value.txt",) and rule.premises]
            self.guiding_rules.extend(lessons)
            guided = bool(lessons) or self.unconditional_repair
            action = macro("guided-repair" if guided else "unguided-repair",
                           [write_value(1 if guided else 2)], checks=[check()], candidate=True)
            return (replace(action, experience_operation=OPERATION, experience_targets=("value.txt",),
                            experience_premises=self.premises()),)
        if stage in {"guided-repair", "unguided-repair"}:
            return (macro("submit", [cat()], checks=[check()], candidate=True, submit=True),)
        return ()

    def update_transition(self, **kwargs):
        self.update_calls += 1
        action = kwargs["action"]
        self.executed.append(action.name)
        lessons = ()
        if action.name == "prefix":
            # This annotation binds to the command actually run by the fixture,
            # not an invented test ID or a claim that the proposal is correct.
            self.assert_public_failure(kwargs["outcome"])
            lessons = (ConditionalExperience(
                operation=OPERATION, target_paths=("value.txt",), premises=self.premises(),
                source_channel="functional_validation", source_index=0,
                lesson=LESSON, next_check=NEXT_CHECK,
            ),)
        return TransitionUpdate(
            TransitionAssessment("exploring", False, "Scripted analysis; official result unknown",
                                 micro_experiences=lessons),
            replace(kwargs["previous"], current_solution=action.name),
        )

    @staticmethod
    def assert_public_failure(outcome):
        if not outcome.functional_validation_attempted or outcome.functional_validation_succeeded:
            raise AssertionError("Fixture must actually observe a failed public counterexample")


class MicroExperienceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "value.txt").write_text("0", encoding="utf-8")
        (self.seed / "check.py").write_text(
            "from pathlib import Path\nassert Path('value.txt').read_text() == '1', 'public zero counterexample'\n",
            encoding="utf-8")
        original_which = shutil.which
        fixture_cat = patch("bestfgs.experience.shutil.which", side_effect=(
            lambda name: sys.executable if name == "cat" else original_which(name)))
        fixture_cat.start()
        self.addCleanup(fixture_cat.stop)

    def run_policy(self, mode, *, policy=None, iterations=3, tools=10, suffix=""):
        policy = policy or MicroGuidedPolicy()
        environment = ReadFixtureEnvironment(self.seed, self.root / (mode + suffix))
        config = BestFGSConfig(experience_mode=mode, max_iterations=iterations, max_total_tool_calls=tools,
                              initial_branching_factor=1, expansion_width=1,
                              base_children_per_node=1, max_children_per_node=1,
                              semantic_node_merge=False, rule_candidate_limit=8)
        checkpoint = self.root / (mode + suffix + "-checkpoint.json")
        result = TaskRunner(environment, policy, config, checkpoint_path=checkpoint).run(
            TaskSpec.create("Repair value with the public zero counterexample", ("value is one",)))
        return result, policy, environment, checkpoint

    def test_preplanning_conditional_lesson_changes_actual_next_action(self):
        off, off_policy, _, _ = self.run_policy("off", iterations=2)
        conditioned, policy, _, _ = self.run_policy("conditioned", iterations=2)
        self.assertEqual(off_policy.executed, ["prefix", "unguided-repair"])
        self.assertEqual(policy.executed, ["prefix", "guided-repair"])
        self.assertTrue(policy.guiding_rules, "An observed conditional micro lesson must reach the planning call")
        self.assertTrue(any(rule.source_count >= 1 and rule.evidence_ids for rule in policy.guiding_rules))
        self.assertTrue(any("check.py" in (rule.guidance + rule.counterexample_guidance) for rule in policy.guiding_rules))
        self.assertTrue(all(not rules for rules in off_policy.seen_rules))
        self.assertEqual(off_policy.seen_contexts[1].current_solution, "prefix")
        self.assertEqual(policy.seen_contexts[1].current_solution, "prefix")
        self.assertEqual((Path(conditioned.best_node.snapshot.location) / "value.txt").read_text(), "1")
        self.assertEqual((Path(off.best_node.snapshot.location) / "value.txt").read_text(), "2")
        self.assertFalse(off.succeeded)
        self.assertFalse(conditioned.succeeded)

    def test_postproposal_soft_match_reaches_child_next_normal_planning(self):
        result, policy, _, _ = self.run_policy("conditioned")
        self.assertEqual(policy.executed, ["prefix", "guided-repair", "submit"])
        child_prompt = next(context for context in policy.seen_contexts if context.current_solution == "guided-repair")
        historical = [item for item in child_prompt.analysis_and_conclusions if "Historical pre-action match" in item]
        self.assertTrue(historical, "A soft decision log alone is insufficient; the child planner must receive it")
        self.assertTrue(any("recheck current premises" in item.lower() for item in historical))
        # This action changed value 0 -> 1, so the inherited note must explicitly
        # be historical rather than certify the old premise in the new snapshot.
        self.assertEqual((Path(result.best_node.snapshot.location) / "value.txt").read_text(), "1")
        projected = project_context_for_prompt(child_prompt, max_chars=14000)
        projected_feedback = json.dumps(projected["analysis_and_conclusions"])
        self.assertIn("Historical pre-action match", projected_feedback)
        self.assertIn("file_contains", projected_feedback,
                      "A surviving receipt prefix is not enough if its actionable premise is truncated")
        self.assertIn("check.py", projected_feedback,
                      "The next normal planner needs the distinguishing public check, not only source IDs")
        self.assertEqual(policy.planning_calls, 3, "No extra review-model request may be inserted")
        self.assertEqual(policy.update_calls, 3)

    def test_unknown_semantic_premise_is_advisory_and_does_not_block_branch(self):
        result, policy, _, _ = self.run_policy("conditioned", iterations=2,
            policy=MicroGuidedPolicy(unconditional_repair=True, unknown_premise=True))
        self.assertEqual(policy.executed, ["prefix", "guided-repair"])
        matches = [entry for entry in result.experience_report.get("decisions", [])
                   if entry["proposed_action"]["name"] == "guided-repair" and entry.get("micro_matches")]
        self.assertTrue(matches, "The test must exercise a real uncertain soft match, not the no-match path")
        self.assertTrue(all(not entry["blocked"] for entry in matches))
        self.assertTrue(any(entry["executed"] for entry in matches))
        self.assertEqual(policy.planning_calls, 2)
        self.assertLessEqual(result.total_tool_calls, result.hard_tool_call_budget)

    def test_experience_annotations_cannot_change_identity_or_priority(self):
        task = TaskSpec.create("No self-awarded memory priority")
        environment = ReadFixtureEnvironment(self.seed, self.root / "priority")
        search = SemanticBestFirstGraphSearch(environment=environment, policy=MicroGuidedPolicy(),
            rule_store=TaskRuleStore(task.task_id), config=BestFGSConfig(experience_mode="conditioned"))
        graph = SearchGraph()
        node = graph.add_root(StructuredContext(task_goal=task.goal), environment.initial_snapshot())
        plain = macro("same-repair", [write_value(1)], candidate=True)
        claimed = replace(plain, experience_operation=OPERATION, experience_targets=("value.txt",),
                          experience_premises=(ExperiencePremise("value.txt", "file_contains", "0"),),
                          applied_rule_ids=("model-claimed-use",), experience_revision="I learned the lesson")
        self.assertEqual(plain.signature(), claimed.signature())
        self.assertEqual(search._priority_for_action(node, plain, 1), search._priority_for_action(node, claimed, 1))

    def test_micro_learning_cannot_extend_existing_iteration_or_tool_budget(self):
        result, policy, environment, _ = self.run_policy("conditioned", iterations=2, tools=3)
        self.assertLessEqual(len(result.transitions), 2)
        self.assertLessEqual(result.total_tool_calls, 3)
        self.assertLessEqual(len(environment.actual_commands), 3)
        self.assertLessEqual(policy.planning_calls, 2)
        self.assertFalse(result.submitted)
        self.assertFalse(result.succeeded)

    def test_micro_audit_saved_but_never_claims_savings_or_official_success(self):
        result, _, _, checkpoint = self.run_policy("conditioned", iterations=2)
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        self.assertTrue(payload["experience_report"].get("micro_experiences"))
        self.assertTrue(payload["task_experiences"])
        self.assertIsNone(payload["official_resolved"])
        self.assertIsNone(result.experience_report["false_block_rate"])
        self.assertIsNone(result.experience_report["causal_tool_calls_saved"])

    @staticmethod
    def projected_compact_feedback(match):
        compact = SemanticBestFirstGraphSearch._compact_micro_feedback(match)
        context = StructuredContext(task_goal="Check the public fixture", analysis_and_conclusions=(
            "Runtime evidence feedback (not a correctness verdict): " + compact,))
        projected = project_context_for_prompt(context, max_chars=14000)["analysis_and_conclusions"]
        if len(projected) != 1:
            raise AssertionError("Compact feedback must fit one normal prompt item")
        return projected[0]

    def test_oversize_compound_conditions_are_omitted_as_a_whole(self):
        premises = [{"subject": f"file_{index}.txt", "predicate": "file_contains", "value": "z" * 130}
                    for index in range(4)]
        # This compound is under the wire-level 900-character bound, but cannot
        # fit the smaller feedback context. Partial if_all would broaden it.
        self.assertLess(len(json.dumps(premises, separators=(",", ":"))), 900)
        match = {"micro_id": "micro-compound-audit-id", "operation": OPERATION,
                 "premises": premises, "next_check": NEXT_CHECK}
        projected = self.projected_compact_feedback(match)
        self.assertIn("Compound conditions omitted", projected)
        self.assertIn("do not infer applicability", projected)
        self.assertIn(match["micro_id"], projected)
        self.assertNotIn("if_all", projected)
        self.assertNotIn("z" * 30, projected)

    def test_feedback_accounts_for_runtime_wrapper_without_truncating_literals(self):
        premises = [{"subject": f"file_{index}.txt", "predicate": "file_contains", "value": "v" * 104}
                    for index in range(2)]
        match = {"micro_id": "micro-boundary-complete-conditions", "operation": OPERATION,
                 "premises": premises, "next_check": ""}
        projected = self.projected_compact_feedback(match)
        if "Compound conditions omitted" in projected:
            self.assertNotIn("if_all", projected)
        else:
            payload = json.loads("{" + projected.partition("{")[2])
            self.assertEqual(payload["if_all"], [[p["subject"], p["predicate"], p["value"]] for p in premises])

    def test_feedback_projection_preserves_literal_whitespace_in_file_predicate(self):
        literal = "zero  remains    distinct"
        match = {"micro_id": "micro-whitespace", "operation": OPERATION,
                 "premises": [{"subject": "value.txt", "predicate": "file_contains", "value": literal}],
                 "next_check": "Run check.py"}
        projected = self.projected_compact_feedback(match)
        payload = json.loads("{" + projected.partition("{")[2])
        self.assertEqual(payload["if_all"], [["value.txt", "file_contains", literal]])


if __name__ == "__main__":
    unittest.main()
