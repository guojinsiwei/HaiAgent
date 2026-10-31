from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

from bestfgs.agent import TaskRunner
from bestfgs.best_first_runtime import BestFGSConfig
from bestfgs.models import (
    CommandResult,
    CommandSpec,
    EnvironmentSnapshot,
    ExecutionOutcome,
    MacroAction,
    ModelCallError,
    TaskSpec,
)
from bestfgs.success_judge import (
    CriterionJudgement,
    IndependentSuccessJudge,
    SuccessJudgeDecision,
)
from examples.demo_counter import CounterEnvironment, CounterPolicy


@dataclass(slots=True)
class ScriptedJudgeClient:
    response: dict
    calls: int = 0
    prompt: str = ""

    def complete_json(self, **kwargs):
        self.calls += 1
        self.prompt = kwargs["user_prompt"]
        return self.response

    def usage_summary(self):
        return {"model_calls": self.calls}


@dataclass(slots=True)
class StaticJudge:
    decision: SuccessJudgeDecision
    calls: int = 0

    def evaluate(self, **kwargs) -> SuccessJudgeDecision:
        self.calls += 1
        return self.decision

    def usage_summary(self):
        return {"judge_calls": self.calls}


@dataclass(slots=True)
class DirectCounterPolicy(CounterPolicy):
    def propose_initial_skeleton(self, **kwargs):
        return (self._action(3),)


def _real_outcome(root: Path) -> tuple[TaskSpec, MacroAction, ExecutionOutcome]:
    before = root / "before"
    after = root / "after"
    before.mkdir()
    after.mkdir()
    (before / "solver.py").write_text("VALUE = 1\n", encoding="utf-8")
    (after / "solver.py").write_text("VALUE = 2\n", encoding="utf-8")
    task = TaskSpec.create("Set the value to two.", ("VALUE equals 2",))
    edit = CommandSpec(("python", "edit.py"), "edit solver")
    test = CommandSpec(("python", "-m", "pytest", "tests/test_solver.py"), "test solver")
    action = MacroAction.create(
        name="repair_value",
        rationale="candidate repair",
        semantic_direction_id="repair",
        semantic_direction_label="Repair value",
        commands=(edit,),
        verification_commands=(test,),
        intent="candidate",
    )
    parent = EnvironmentSnapshot("before", str(before), "before", "before")
    result = EnvironmentSnapshot(
        "after",
        str(after),
        "after",
        "after",
        {"changed_paths_from_parent": ["solver.py"]},
    )
    outcome = ExecutionOutcome(
        parent,
        result,
        action,
        (CommandResult(edit, 0, "edited", "", 0.0),),
        validation_results=(),
        functional_validation_results=(
            CommandResult(test, 0, "1 passed", "", 0.0),
        ),
    )
    return task, action, outcome


def _guard_removal_outcome(root: Path) -> tuple[TaskSpec, MacroAction, ExecutionOutcome]:
    before = root / "guard-before"
    after = root / "guard-after"
    before.mkdir()
    after.mkdir()
    (before / "loader.py").write_text(
        "def load(items):\n    if not items:\n        return []\n    return list(items)\n",
        encoding="utf-8",
    )
    (after / "loader.py").write_text(
        "def load(items):\n    return list(items)\n",
        encoding="utf-8",
    )
    task = TaskSpec.create(
        "Support iterable loaders without regressing empty inputs.",
        ("New iterables load and empty inputs retain their behavior",),
    )
    edit = CommandSpec(("python", "edit.py"), "remove loader guard")
    test = CommandSpec(("python", "-m", "pytest"), "run broad suite")
    action = MacroAction.create(
        name="remove_guard",
        rationale="broaden accepted inputs",
        semantic_direction_id="repair",
        semantic_direction_label="Repair loader",
        commands=(edit,),
        verification_commands=(test,),
        intent="candidate",
    )
    parent = EnvironmentSnapshot("guard-before", str(before), "before", "before")
    result = EnvironmentSnapshot(
        "guard-after",
        str(after),
        "after",
        "after",
        {"changed_paths_from_parent": ["loader.py"]},
    )
    outcome = ExecutionOutcome(
        parent,
        result,
        action,
        (CommandResult(edit, 0, "edited", "", 0.0),),
        functional_validation_results=(
            CommandResult(test, 0, "518 tests passed", "", 0.0),
        ),
    )
    return task, action, outcome


def _inline_only_outcome(root: Path) -> tuple[TaskSpec, MacroAction, ExecutionOutcome]:
    task, action, outcome = _real_outcome(root)
    inline = CommandSpec(
        ("python", "-c", "assert 2 == 2"),
        "solver-authored focused probe",
    )
    action = replace(action, verification_commands=(inline,))
    outcome = replace(
        outcome,
        action=action,
        functional_validation_results=(CommandResult(inline, 0, "probe passed", "", 0.0),),
    )
    return task, action, outcome


class IndependentSuccessJudgeTests(unittest.TestCase):
    def test_stronger_tests_can_verify_existing_patch_without_cosmetic_edit(self):
        class ReverifyPolicy(DirectCounterPolicy):
            def propose_actions(self, **kwargs):
                action = self._action(0)
                return (replace(action, semantic_direction_id="verify_more",
                                semantic_direction_label="verify more"),)
        class TwoPassJudge:
            calls = 0
            def evaluate(self, **kwargs):
                self.calls += 1
                return SuccessJudgeDecision(
                    verdict="insufficient_evidence" if self.calls == 1 else "pass",
                    summary="Need one additional independent boundary test" if self.calls == 1 else "All checks pass",
                    missing_checks=("Exercise boundary",) if self.calls == 1 else (),
                )
            def usage_summary(self):
                return {"judge_calls": self.calls}
        judge = TwoPassJudge()
        result = TaskRunner(CounterEnvironment(), ReverifyPolicy(), BestFGSConfig(
            max_iterations=6, max_total_tool_calls=30, initial_branching_factor=1,
            success_judge_mode="required",
        ), success_judge=judge).run(TaskSpec.create("Reach counter value 3.", ("The counter equals 3.",)))
        self.assertTrue(result.succeeded)
        self.assertEqual(result.interaction_rounds, 2)
        self.assertFalse(result.transitions[-1].outcome.workspace_changed)
        self.assertTrue(result.transitions[-1].assessment.candidate_success)

    def test_schema_repair_uses_same_candidate_and_only_valid_decision_budget(self):
        bad = {"verdict": "pass"}
        good = {
            "verdict": "PASS", "summary": "Focused tests passed.",
            "criteria": [{"criterion": "VALUE equals 2", "status": "satisfied",
                          "evidence_ids": ["functional_test-1"], "reason": "Explicit assertion"}],
            "regression_risk": "low", "missing_checks": [], "risk_checks": [],
        }
        class Client:
            def __init__(self):
                self.calls = []
            def complete_json(self, **kwargs):
                self.calls.append(kwargs["user_prompt"])
                return bad if len(self.calls) == 1 else good
        client = Client()
        judge = IndependentSuccessJudge(client, max_calls=1)
        with tempfile.TemporaryDirectory() as directory:
            task, action, outcome = _real_outcome(Path(directory))
            result = judge.evaluate(task=task, action=action, outcome=outcome)
            cached = judge.evaluate(task=task, action=action, outcome=outcome)
        self.assertTrue(result.passed)
        self.assertTrue(cached.cache_hit)
        self.assertEqual(len(client.calls), 2)
        self.assertIn("Correct the JSON using ONLY the same evidence", client.calls[1])
        self.assertEqual(judge.usage_summary()["valid_judge_calls"], 1)
        self.assertTrue(judge.budget_exhausted)

    def test_judge_audits_cumulative_patch_and_final_file_inventory(self):
        client = ScriptedJudgeClient({})
        judge = IndependentSuccessJudge(client)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task, action, outcome = _real_outcome(root)
            initial = root / "initial"
            initial.mkdir()
            (initial / "solver.py").write_text("VALUE = 0\n")
            (initial / "guard.py").write_text("if not data:\n    raise ValueError()\n")
            (root / "after" / "cmain").write_text("leftover binary")
            result = replace(outcome.resulting_snapshot,
                             metadata={"changed_paths_from_root": ["solver.py", "guard.py", "cmain"]})
            outcome = replace(outcome, resulting_snapshot=result,
                              audit_baseline_snapshot=EnvironmentSnapshot("root", str(initial), "root", "root"))
            with self.assertRaises(ModelCallError):
                judge.evaluate(task=task, action=action, outcome=outcome)
        self.assertIn("-VALUE = 0", client.prompt)
        self.assertIn("risk-removed-control-flow", client.prompt)
        self.assertIn("cmain", client.prompt)
        self.assertEqual(judge.usage_summary()["valid_judge_calls"], 0)

    def test_judge_budget_exhaustion_does_not_consume_search_budget_or_invent_gap(self):
        task = TaskSpec.create("Reach counter value 3.", ("The counter equals 3.",))
        judge = StaticJudge(SuccessJudgeDecision(
            verdict="insufficient_evidence", summary="No requests remain",
            audit_status="budget_exhausted",
        ))
        result = TaskRunner(CounterEnvironment(), DirectCounterPolicy(), BestFGSConfig(
            max_iterations=24, max_total_tool_calls=80, initial_branching_factor=1,
            success_judge_mode="required",
        ), success_judge=judge).run(task)
        self.assertNotEqual(result.stop_reason, "judge_budget_exhausted")
        self.assertFalse(result.succeeded)
        self.assertNotIn("Independent verification gap", str(result.transitions[0].state_after.unresolved_issues))

    def test_pass_requires_cited_functional_evidence_and_is_cached(self) -> None:
        response = {
            "verdict": "pass",
            "summary": "The patch is exercised by the focused test.",
            "criteria": [
                {
                    "criterion": "VALUE equals 2",
                    "status": "satisfied",
                    "evidence_ids": ["functional_test-1"],
                    "reason": "The focused test passed after the edit.",
                }
            ],
            "regression_risk": "low",
            "missing_checks": [],
        }
        client = ScriptedJudgeClient(response)
        judge = IndependentSuccessJudge(client)
        with tempfile.TemporaryDirectory() as directory:
            task, action, outcome = _real_outcome(Path(directory))
            first = judge.evaluate(task=task, action=action, outcome=outcome)
            second = judge.evaluate(task=task, action=action, outcome=outcome)

        self.assertTrue(first.passed)
        self.assertTrue(second.cache_hit)
        self.assertEqual(client.calls, 1)
        self.assertIn("-VALUE = 1", client.prompt)
        self.assertIn("+VALUE = 2", client.prompt)

    def test_pass_cannot_cite_unknown_or_nonfunctional_evidence(self) -> None:
        response = {
            "verdict": "pass",
            "summary": "Unsupported pass.",
            "criteria": [
                {
                    "criterion": "VALUE equals 2",
                    "status": "satisfied",
                    "evidence_ids": ["action-1"],
                    "reason": "Only the edit command is cited.",
                }
            ],
            "regression_risk": "low",
            "missing_checks": [],
        }
        judge = IndependentSuccessJudge(ScriptedJudgeClient(response))
        with tempfile.TemporaryDirectory() as directory:
            task, action, outcome = _real_outcome(Path(directory))
            with self.assertRaises(ModelCallError):
                judge.evaluate(task=task, action=action, outcome=outcome)

    def test_inline_probe_alone_is_downgraded_to_insufficient_evidence(self) -> None:
        response = {
            "verdict": "pass",
            "summary": "The custom probe passed.",
            "criteria": [
                {
                    "criterion": "VALUE equals 2",
                    "status": "satisfied",
                    "evidence_ids": ["functional_test-1"],
                    "reason": "The inline assertion passed.",
                }
            ],
            "risk_checks": [],
            "regression_risk": "low",
            "missing_checks": [],
        }
        client = ScriptedJudgeClient(response)
        judge = IndependentSuccessJudge(client)
        with tempfile.TemporaryDirectory() as directory:
            task, action, outcome = _inline_only_outcome(Path(directory))
            decision = judge.evaluate(task=task, action=action, outcome=outcome)

        self.assertEqual(decision.verdict, "insufficient_evidence")
        self.assertEqual(decision.regression_risk, "medium")
        self.assertIn("project regression test", decision.missing_checks[0])
        self.assertIn('"verification_scope": "inline_probe"', client.prompt)

    def test_guard_removal_cannot_hide_behind_generic_passing_suite(self) -> None:
        response = {
            "verdict": "pass",
            "summary": "The broad suite passed.",
            "criteria": [
                {
                    "criterion": "New iterables load and empty inputs retain their behavior",
                    "status": "satisfied",
                    "evidence_ids": ["functional_test-1"],
                    "reason": "A large suite passed.",
                }
            ],
            # Omitting the deterministic risk checks must make PASS schema-invalid.
            "risk_checks": [],
            "regression_risk": "low",
            "missing_checks": [],
        }
        client = ScriptedJudgeClient(response)
        judge = IndependentSuccessJudge(client)
        with tempfile.TemporaryDirectory() as directory:
            task, action, outcome = _guard_removal_outcome(Path(directory))
            with self.assertRaises(ModelCallError):
                judge.evaluate(task=task, action=action, outcome=outcome)

        self.assertIn("risk-removed-control-flow", client.prompt)
        self.assertIn("risk-deletion-only", client.prompt)
        self.assertIn("after_all_candidate_edits", client.prompt)

    def test_guard_removal_can_request_a_specific_counterexample(self) -> None:
        response = {
            "verdict": "insufficient_evidence",
            "summary": "The removed empty-input guard lacks focused regression evidence.",
            "criteria": [
                {
                    "criterion": "New iterables load and empty inputs retain their behavior",
                    "status": "unproven",
                    "evidence_ids": ["functional_test-1"],
                    "reason": "The suite total does not show the empty-input boundary.",
                }
            ],
            "risk_checks": [
                {
                    "risk_id": "risk-removed-control-flow",
                    "status": "unresolved",
                    "evidence_ids": [],
                    "reason": "No named test exercises the removed empty-input branch.",
                },
                {
                    "risk_id": "risk-deletion-only",
                    "status": "unresolved",
                    "evidence_ids": [],
                    "reason": "No replacement behavior is demonstrated for empty inputs.",
                },
            ],
            "regression_risk": "high",
            "missing_checks": ["Test an empty input after the final edit."],
        }
        judge = IndependentSuccessJudge(ScriptedJudgeClient(response))
        with tempfile.TemporaryDirectory() as directory:
            task, action, outcome = _guard_removal_outcome(Path(directory))
            decision = judge.evaluate(task=task, action=action, outcome=outcome)

        self.assertEqual(decision.verdict, "insufficient_evidence")
        self.assertEqual(len(decision.risk_checks), 2)

    def test_required_judge_controls_verified_success(self) -> None:
        task = TaskSpec.create("Reach counter value 3.", ("The counter equals 3.",))
        rejected = StaticJudge(
            SuccessJudgeDecision(
                verdict="insufficient_evidence",
                summary="The selected check is too narrow.",
                missing_checks=("Run a broader counter regression.",),
            )
        )
        rejected_result = TaskRunner(
            CounterEnvironment(),
            DirectCounterPolicy(),
            BestFGSConfig(
                max_iterations=1,
                max_total_tool_calls=12,
                initial_branching_factor=1,
                success_judge_mode="required",
            ),
            success_judge=rejected,
        ).run(task)
        self.assertFalse(rejected_result.succeeded)
        self.assertTrue(rejected_result.transitions[0].assessment.candidate_success)
        self.assertEqual(
            rejected_result.transitions[0].assessment.judge_verdict,
            "insufficient_evidence",
        )
        self.assertIn(
            "Independent verification gap",
            rejected_result.transitions[0].state_after.unresolved_issues[-1],
        )

        accepted = StaticJudge(
            SuccessJudgeDecision(
                verdict="pass",
                summary="Independent evidence is complete.",
                criteria=(
                    CriterionJudgement(
                        "The counter equals 3.",
                        "satisfied",
                        ("functional_test-1",),
                        "verified",
                    ),
                ),
                regression_risk="low",
            )
        )
        accepted_result = TaskRunner(
            CounterEnvironment(),
            DirectCounterPolicy(),
            BestFGSConfig(
                max_iterations=1,
                max_total_tool_calls=12,
                initial_branching_factor=1,
                success_judge_mode="required",
            ),
            success_judge=accepted,
        ).run(task)
        self.assertTrue(accepted_result.succeeded)
        self.assertEqual(accepted_result.success_judge_calls, 1)


if __name__ == "__main__":
    unittest.main()
