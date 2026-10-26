"""Delivery contract regressions using real Git files and public local tests.

No model, Docker, benchmark download, or hidden/reference solution is involved.
The scripted policy intentionally overclaims success: only explicit delivery,
actual patch evidence, and complete execution may authorize submission.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from bestfgs.agent import TaskRunner
from bestfgs.best_first_runtime import BestFGSConfig
from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.models import (
    CommandSpec, InitialSemanticPlan, MacroAction, SemanticDirection,
    TaskSpec, TransitionAssessment, TransitionUpdate,
)
from bestfgs.submission import inspect_git_submission


def python_command(source: str, description: str) -> CommandSpec:
    return CommandSpec((sys.executable, "-c", source), description)


def edit(value: int) -> CommandSpec:
    return python_command(
        f"from pathlib import Path; Path('answer.py').write_text('VALUE = {value}\\n')",
        f"write source value {value}",
    )


def read_source() -> CommandSpec:
    return python_command(
        "from pathlib import Path; print(Path('answer.py').read_text())",
        "inspect current source without changing it",
    )


def public_test(method: str = "test_repair") -> CommandSpec:
    return CommandSpec(
        (sys.executable, "-B", "-m", "unittest", f"tests.test_answer.PublicTests.{method}"),
        f"run existing public test {method}",
    )


def action(name, commands, verification=(), *, intent="candidate", submit=False,
           direction="repair"):
    return MacroAction.create(
        name=name, rationale="offline delivery contract fixture",
        semantic_direction_id=direction, semantic_direction_label=direction,
        commands=tuple(commands), verification_commands=tuple(verification),
        intent=intent, submit=submit,
    )


class ScriptedPolicy:
    """Choose from current context, not the number of speculative proposals."""

    def __init__(self, actions, *, crash_on_update=False):
        self.actions = tuple(actions)
        self.crash_on_update = crash_on_update
        self.updated = []

    def propose_initial_plan(self, **kwargs):
        directions = tuple(dict.fromkeys(a.semantic_direction_id for a in self.actions))
        return InitialSemanticPlan(
            tuple(SemanticDirection(name, name) for name in directions), self.actions[0],
        )

    def propose_actions(self, **kwargs):
        current = kwargs["context"].current_solution
        index = int(current.removeprefix("fixture-step-")) if current.startswith("fixture-step-") else 0
        return self.actions[index:index + 1]

    def update_transition(self, **kwargs):
        if self.crash_on_update:
            raise RuntimeError("offline fixture: assessment failed after real source edit")
        current_action = kwargs["action"]
        self.updated.append(current_action.name)
        index = next(i for i, a in enumerate(self.actions) if a.name == current_action.name)
        return TransitionUpdate(
            # Even a fully covered model assessment is not an official verdict.
            TransitionAssessment(
                "covered", True, "scripted model claims every criterion is met",
                kwargs["task"].required_success_criteria,
            ),
            replace(
                kwargs["previous"], current_solution=f"fixture-step-{index + 1}",
                environment_summary=f"offline fixture completed {current_action.name}",
            ),
        )


class TruncatedVerificationEnvironment(ForkedWorkspaceEnvironment):
    """Simulate the executor exhausting allowance partway through submission."""

    def execute(self, snapshot, action, max_commands):
        if action.submit:
            max_commands = min(max_commands, 2)  # one read plus only one of two checks
        return super().execute(snapshot, action, max_commands)


class FailingFinalVerificationEnvironment(ForkedWorkspaceEnvironment):
    def _execute_command(self, snapshot_dir, command):
        self.actual_calls = getattr(self, "actual_calls", 0) + 1
        return super()._execute_command(snapshot_dir, command)

    def verify(self, snapshot, commands):
        self.verify_count = getattr(self, "verify_count", 0) + 1
        results = super().verify(snapshot, commands)
        if self.verify_count >= 3:
            raise RuntimeError("failure after executing final verification")
        return results


@unittest.skipUnless(shutil.which("git"), "real Git is required for delivery regressions")
class DeliveryRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "answer.py").write_text("VALUE = 0\n", encoding="utf-8")
        (self.seed / "tests").mkdir()
        (self.seed / "tests/__init__.py").write_text("", encoding="utf-8")
        (self.seed / "tests/test_answer.py").write_text(
            "import unittest\nimport answer\n\n"
            "class PublicTests(unittest.TestCase):\n"
            "    def test_repair(self):\n        self.assertEqual(answer.VALUE, 1)\n"
            "    def test_type(self):\n        self.assertIsInstance(answer.VALUE, int)\n",
            encoding="utf-8",
        )
        self.git("init", "--quiet")
        self.git("-c", "core.autocrlf=false", "add", "--all")
        self.git(
            "-c", "user.name=DeliveryTest", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "public fixture",
        )
        self.base = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.seed, check=True, capture_output=True,
        ).stdout

    def run_actions(self, actions, *, environment_class=ForkedWorkspaceEnvironment,
                    max_tools=10, checkpoint=None, crash_on_update=False):
        self.policy = ScriptedPolicy(actions, crash_on_update=crash_on_update)
        self.environment = environment_class(self.seed, self.root / "run")
        self.config = BestFGSConfig(
            max_iterations=len(actions), max_total_tool_calls=max_tools,
            initial_branching_factor=1, expansion_width=1,
            base_children_per_node=1, max_children_per_node=1,
            semantic_node_merge=False,
        )
        self.assertEqual(self.config.termination_mode, "explicit_submission")
        return TaskRunner(
            self.environment, self.policy, self.config, checkpoint_path=checkpoint,
        ).run(TaskSpec.create("Change the source value to one", ("Public repair test passes",)))

    def patch_for(self, result):
        return inspect_git_submission(Path(result.best_node.snapshot.location), self.base)

    def assert_not_official_success(self, result):
        self.assertFalse(result.succeeded)
        self.assertFalse(result.verified_success)
        self.assertIsInstance(result.delivery, dict)
        self.assertIsNone(result.delivery.get("official_resolved"))
        self.assertEqual((self.seed / "answer.py").read_text(), "VALUE = 0\n")

    def test_public_validation_and_model_claim_do_not_stop_without_submit(self):
        result = self.run_actions([
            action("repair", [edit(1)], [public_test()]),
            action("review", [read_source()], intent="explore", direction="review"),
        ])
        self.assertEqual(self.policy.updated, ["repair", "review"])
        self.assertTrue(result.transitions[0].outcome.functional_validation_succeeded)
        self.assertFalse(result.submitted)
        self.assertNotEqual(result.stop_reason, "verified_success")
        self.assertTrue(self.patch_for(result).has_changes)
        self.assert_not_official_success(result)

    def test_same_covered_direction_can_reach_read_only_explicit_submission(self):
        result = self.run_actions([
            action("repair", [edit(1)], [public_test()]),
            action("submit", [read_source()], [public_test()], submit=True),
        ])
        self.assertEqual(self.policy.updated, ["repair", "submit"])
        self.assertTrue(result.submitted)
        self.assertEqual(result.stop_reason, "submitted")
        self.assertTrue(result.delivery.get("local_validation_passed"))
        self.assertTrue(self.patch_for(result).has_changes)
        self.assertLessEqual(result.total_tool_calls, self.config.max_total_tool_calls)
        self.assert_not_official_success(result)

    def test_first_functional_failure_keeps_a_nonempty_legal_draft(self):
        result = self.run_actions([action("incomplete-repair", [edit(2)], [public_test()])])
        self.assertFalse(result.transitions[0].outcome.functional_validation_succeeded)
        self.assertTrue(self.patch_for(result).has_changes)
        self.assertEqual((Path(result.best_node.snapshot.location) / "answer.py").read_text(), "VALUE = 2\n")
        self.assertFalse(result.submitted)
        self.assertFalse(result.delivery.get("local_validation_passed"))
        self.assert_not_official_success(result)

    def test_exploration_source_change_is_delivered_at_budget_end(self):
        result = self.run_actions([action("exploratory-repair", [edit(1)], intent="explore")])
        self.assertTrue(self.patch_for(result).has_changes)
        self.assertFalse(result.submitted)
        self.assert_not_official_success(result)

    def test_git_index_only_changes_never_authorize_submission(self):
        result = self.run_actions([
            action("index-only", [CommandSpec(
                ("git", "update-index", "--assume-unchanged", "answer.py"), "change only Git index flags",
            )], intent="explore"),
            action("empty-submit", [read_source()], [public_test("test_type")], submit=True),
        ])
        self.assertEqual(self.policy.updated, ["index-only", "empty-submit"])
        indexed_snapshot = Path(result.transitions[0].outcome.resulting_snapshot.location)
        self.assertNotEqual(
            (indexed_snapshot / ".git/index").read_bytes(),
            (self.seed / ".git/index").read_bytes(),
        )
        self.assertTrue(result.transitions[-1].outcome.functional_validation_succeeded)
        self.assertFalse(self.patch_for(result).has_changes)
        self.assertFalse(result.submitted)
        self.assertNotEqual(result.stop_reason, "submitted")
        self.assert_not_official_success(result)

    def test_submit_that_changes_source_is_rejected_but_new_draft_survives(self):
        result = self.run_actions([
            action("draft", [edit(2)], intent="explore"),
            action("edit-and-submit", [edit(1)], [public_test()], submit=True),
        ])
        self.assertEqual(self.policy.updated, ["draft", "edit-and-submit"])
        self.assertFalse(result.submitted)
        self.assertNotEqual(result.stop_reason, "submitted")
        self.assertTrue(self.patch_for(result).has_changes)
        self.assertEqual((Path(result.best_node.snapshot.location) / "answer.py").read_text(), "VALUE = 1\n")
        self.assert_not_official_success(result)

    def test_partial_submission_verification_cannot_be_accepted(self):
        result = self.run_actions([
            action("draft", [edit(1)], intent="explore"),
            action("partial-submit", [read_source()], [public_test(), public_test("test_type")], submit=True),
        ], environment_class=TruncatedVerificationEnvironment, max_tools=4)
        self.assertEqual(self.policy.updated, ["draft", "partial-submit"])
        self.assertEqual(len(result.transitions[-1].outcome.functional_validation_results), 1)
        self.assertFalse(result.submitted)
        self.assertNotEqual(result.stop_reason, "submitted")
        self.assertLessEqual(result.total_tool_calls, 4)
        self.assertTrue(self.patch_for(result).has_changes)
        self.assert_not_official_success(result)

    def test_assessment_exception_checkpoint_keeps_the_real_source_edit(self):
        checkpoint = self.root / "checkpoint.json"
        with self.assertRaisesRegex(RuntimeError, "assessment failed"):
            self.run_actions(
                [action("draft-before-error", [edit(1)], intent="explore")],
                checkpoint=checkpoint, crash_on_update=True,
            )
        self.assertTrue(checkpoint.is_file())
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        self.assertFalse(saved["succeeded"])
        self.assertFalse(saved.get("verified_success", False))
        self.assertFalse(saved.get("submitted", False))
        candidate = Path(saved["best_workspace"])
        self.assertTrue(inspect_git_submission(candidate, self.base).has_changes)
        self.assertEqual((candidate / "answer.py").read_text(), "VALUE = 1\n")
        self.assertEqual((self.seed / "answer.py").read_text(), "VALUE = 0\n")

    def test_complete_submit_at_exact_budget_reuses_its_fresh_checks(self):
        result = self.run_actions([
            action("draft", [edit(1)], intent="explore"),
            action("submit", [read_source()], [public_test()], submit=True),
        ], max_tools=3)
        self.assertTrue(result.submitted)
        self.assertEqual(result.total_tool_calls, 3)
        self.assertEqual(result.final_verification_tool_calls, 0)
        self.assertTrue(result.delivery["local_validation_passed"])
        self.assertEqual(result.delivery["final_verification_status"], "reused_submission_checks")
        self.assert_not_official_success(result)

    def test_final_verification_exception_is_not_free_budget(self):
        result = self.run_actions([
            action("first", [edit(1)], [public_test()], direction="first"),
            action("second", [edit(2)], [public_test("test_type")], direction="second"),
        ], environment_class=FailingFinalVerificationEnvironment, max_tools=5)
        self.assertEqual(self.environment.actual_calls, 5)
        self.assertEqual(result.total_tool_calls, 5)
        self.assertEqual(result.final_verification_tool_calls, 1)
        self.assertTrue(self.patch_for(result).has_changes)
        self.assert_not_official_success(result)

    def test_no_budget_for_recheck_is_not_a_failed_test(self):
        result = self.run_actions([
            action("repair", [edit(1)], [public_test()]),
        ], max_tools=2)
        self.assertFalse(result.submitted)
        self.assertTrue(result.delivery["local_validation_passed"])
        self.assertEqual(result.delivery["validation_status"], "passed")
        self.assertEqual(result.delivery["final_verification_status"], "skipped_budget")
        self.assert_not_official_success(result)

    def test_changed_artifact_cannot_inherit_old_passing_checks(self):
        class ChangedArtifactPolicy(ScriptedPolicy):
            def update_transition(self, **kwargs):
                result = super().update_transition(**kwargs)
                location = Path(kwargs["outcome"].resulting_snapshot.location)
                (location / "answer.py").write_text("VALUE = 2\n")
                return result
        config = BestFGSConfig(max_iterations=1, max_total_tool_calls=4)
        result = TaskRunner(
            ForkedWorkspaceEnvironment(self.seed, self.root / "runs"),
            ChangedArtifactPolicy([action("repair", [edit(1)], [public_test()])]), config,
        ).run(TaskSpec.create("Repair source", ("Public repair test passes",)))
        self.assertTrue(self.patch_for(result).has_changes)
        self.assertFalse(result.delivery["local_validation_passed"])
        self.assertEqual(result.delivery["final_verification_status"], "artifact_changed")
        self.assertFalse(result.submitted)
        self.assert_not_official_success(result)


if __name__ == "__main__":
    unittest.main()
