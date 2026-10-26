"""Controlled task-local memory regressions, not benchmark success claims.

The policy is scripted and the direct cat tool is a local deterministic fixture.
Python public checks and forked snapshot handling use the real environment.
"""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.agent import TaskRunner
from bestfgs.best_first import SemanticBestFirstGraphSearch
from bestfgs.best_first_runtime import BestFGSConfig
from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.models import (
    CommandResult, CommandSpec, InitialSemanticPlan, MacroAction, SearchGraph,
    SemanticDirection, StructuredContext, TaskSpec, TransitionAssessment, TransitionUpdate,
)
from bestfgs.rules import TaskRuleStore


def macro(name, commands, *, checks=(), candidate=False, submit=False, direction="repair", ids=()):
    return MacroAction.create(
        name=name, rationale="controlled memory fixture", semantic_direction_id=direction,
        semantic_direction_label=direction, commands=tuple(commands),
        verification_commands=tuple(checks), intent="candidate" if candidate else "explore",
        submit=submit, applied_rule_ids=ids,
    )


def cat(path="value.txt"):
    return CommandSpec(("cat", path), "direct deterministic file read")


def write_value(value):
    return CommandSpec((sys.executable, "-c",
        f"from pathlib import Path; Path('value.txt').write_text('{value}')"), "edit fixture source")


def check():
    return CommandSpec((sys.executable, "check.py"), "public fixture counterexample")


class ReadFixtureEnvironment(ForkedWorkspaceEnvironment):
    def _execute_command(self, snapshot_dir, command):
        self.actual_commands = getattr(self, "actual_commands", [])
        self.actual_commands.append(command)
        if command.argv[0] == "cat":
            value = (snapshot_dir / command.argv[1]).read_text(encoding="utf-8")
            return CommandResult(command, 0, value, "", 0.0)
        return super()._execute_command(snapshot_dir, command)


class RepeatedReadPolicy:
    def __init__(self):
        self.seen_rules = []
        self.executed = []

    def propose_initial_plan(self, **kwargs):
        self.seen_rules.append(kwargs["rules"])
        return InitialSemanticPlan((SemanticDirection("repair", "repair"),), macro("prefix", [cat()]))

    def propose_actions(self, **kwargs):
        self.seen_rules.append(kwargs["rules"])
        stage = kwargs["context"].current_solution
        if stage == "prefix":
            return (macro("same-read-new-name", [cat()]),
                    macro("repair", [write_value(1)], candidate=True))
        if stage == "same-read-new-name":
            return (macro("repair", [write_value(1)], candidate=True),)
        if stage == "repair":
            return (macro("submit", [cat()], checks=[check()], candidate=True, submit=True),)
        return ()

    def update_transition(self, **kwargs):
        self.executed.append(kwargs["action"].name)
        return TransitionUpdate(
            TransitionAssessment("exploring", False, "Only a fixture observation, no official claim"),
            replace(kwargs["previous"], current_solution=kwargs["action"].name),
        )


class CounterexamplePolicy(RepeatedReadPolicy):
    def propose_initial_plan(self, **kwargs):
        return InitialSemanticPlan((SemanticDirection("repair", "repair"),),
            macro("failed-reproduction", [cat()], checks=[check()], candidate=True))

    def propose_actions(self, **kwargs):
        stage = kwargs["context"].current_solution
        if stage == "failed-reproduction":
            # Deliberately omit the public check: conditioned experience must
            # replay the previously observed counterexample within the budget.
            return (macro("repair", [write_value(1)], candidate=True),)
        if stage == "repair":
            return (macro("submit", [cat()], checks=[check()], candidate=True, submit=True),)
        return ()


class ExperienceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "value.txt").write_text("0", encoding="utf-8")
        (self.seed / "check.py").write_text(
            "from pathlib import Path\nassert Path('value.txt').read_text() == '1', 'public value counterexample'\n",
            encoding="utf-8",
        )
        # Fixture cat is dispatched in Python above. Give its deterministic
        # capability token a real, immutable executable for dependency auditing.
        import shutil
        original_which = shutil.which
        self.which = patch("bestfgs.experience.shutil.which", side_effect=(
            lambda executable: sys.executable if executable == "cat" else original_which(executable)
        ))
        self.which.start()
        self.addCleanup(self.which.stop)

    def run_policy(self, mode, policy=None, *, max_iterations=4, max_tools=8):
        policy = policy or RepeatedReadPolicy()
        environment = ReadFixtureEnvironment(self.seed, self.root / ("run-" + mode))
        config = BestFGSConfig(
            experience_mode=mode, max_iterations=max_iterations, max_total_tool_calls=max_tools,
            initial_branching_factor=1, expansion_width=1,
            base_children_per_node=1, max_children_per_node=1, semantic_node_merge=False,
        )
        checkpoint = self.root / (mode + "-checkpoint.json")
        result = TaskRunner(environment, policy, config, checkpoint_path=checkpoint).run(
            TaskSpec.create("Repair the public value", ("value is one",)),
        )
        return result, policy, environment

    def test_same_prefix_retains_history_and_avoids_only_redundant_read(self):
        off, off_policy, off_env = self.run_policy("off")
        conditioned, new_policy, new_env = self.run_policy("conditioned")
        self.assertEqual(off_policy.executed, ["prefix", "same-read-new-name", "repair", "submit"])
        self.assertEqual(new_policy.executed, ["prefix", "repair", "submit"])
        self.assertTrue(off.submitted)
        self.assertTrue(conditioned.submitted)
        self.assertTrue(all(not rules for rules in off_policy.seen_rules))
        self.assertTrue(any(new_policy.seen_rules[1:]))
        self.assertEqual(off.total_tool_calls, conditioned.total_tool_calls + 1)
        self.assertEqual(len(off_env.actual_commands), len(new_env.actual_commands) + 1)
        self.assertTrue(conditioned.task_experiences)
        self.assertIsNone(conditioned.experience_report["causal_tool_calls_saved"])
        self.assertIsNone(conditioned.experience_report["false_block_rate"])
        self.assertFalse(conditioned.succeeded)
        payload = json.loads((self.root / "conditioned-checkpoint.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["experience_mode"], "conditioned")
        self.assertTrue(payload["task_experiences"])
        self.assertIsNone(payload["official_resolved"])

    def test_citations_and_revision_claims_cannot_raise_priority(self):
        task = TaskSpec.create("same task")
        environment = ReadFixtureEnvironment(self.seed, self.root / "priority")
        search = SemanticBestFirstGraphSearch(
            environment=environment, policy=RepeatedReadPolicy(), rule_store=TaskRuleStore(task.task_id),
            config=BestFGSConfig(experience_mode="conditioned"),
        )
        graph = SearchGraph()
        node = graph.add_root(StructuredContext(task_goal=task.goal), environment.initial_snapshot())
        plain = macro("read", [cat()])
        cited = replace(plain, applied_rule_ids=("invented",), avoided_rule_ids=("invented2",),
                        experience_revision="I changed my premise")
        self.assertEqual(plain.signature(), cited.signature())
        self.assertEqual(search._priority_for_action(node, plain, 1), search._priority_for_action(node, cited, 1))

    def test_wrong_task_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            BestFGSConfig(experience_mode="silent_magic").validate()

    def test_repeated_candidate_evaluation_cannot_erase_execution_receipt(self):
        task = TaskSpec.create("Audit actual execution")
        environment = ReadFixtureEnvironment(self.seed, self.root / "receipt")
        search = SemanticBestFirstGraphSearch(
            environment=environment, policy=RepeatedReadPolicy(), rule_store=TaskRuleStore(task.task_id),
            config=BestFGSConfig(),
        )
        graph = SearchGraph()
        node = graph.add_root(StructuredContext(task_goal=task.goal), environment.initial_snapshot())
        proposal = macro("read", [cat()])
        search._evaluate_action_experience(node, proposal)
        key = search._experience_decision_key(node, proposal)
        receipt = search._experience_decisions[key]
        receipt.update(executed=True, actual_tool_calls=1)
        search._evaluate_action_experience(node, proposal)
        self.assertIs(search._experience_decisions[key], receipt)
        self.assertTrue(receipt["executed"])
        self.assertEqual(receipt["actual_tool_calls"], 1)

    def test_task_experiences_do_not_leak_between_runs(self):
        first, first_policy, _ = self.run_policy("conditioned")
        second, second_policy, _ = self.run_policy("off")
        first_ids = {row["task_id"] for row in first.task_experiences}
        second_ids = {row["task_id"] for row in second.task_experiences}
        self.assertFalse(first_ids & second_ids)
        self.assertEqual(first_policy.seen_rules[0], ())
        self.assertEqual(second_policy.seen_rules[0], ())

    def test_failed_public_counterexample_is_replayed_on_new_patch(self):
        result, policy, environment = self.run_policy(
            "conditioned", CounterexamplePolicy(), max_iterations=3,
        )
        self.assertEqual(policy.executed, ["failed-reproduction", "repair", "submit"])
        self.assertFalse(result.transitions[0].outcome.functional_validation_succeeded)
        self.assertEqual(result.transitions[1].action.verification_commands, (check(),))
        self.assertTrue(result.transitions[1].outcome.functional_validation_succeeded)
        self.assertTrue(result.submitted)
        self.assertEqual(result.total_tool_calls, 6)
        self.assertEqual(len(environment.actual_commands), 6)
        self.assertLessEqual(result.total_tool_calls, result.hard_tool_call_budget)

    def test_failed_counterexample_cannot_borrow_old_pass_or_extra_budget(self):
        result, _, environment = self.run_policy(
            "conditioned", CounterexamplePolicy(), max_iterations=3, max_tools=4,
        )
        self.assertFalse(result.submitted)
        self.assertFalse(result.succeeded)
        self.assertLessEqual(result.total_tool_calls, 4)
        self.assertLessEqual(len(environment.actual_commands), 4)
        self.assertTrue(result.delivery["has_patch"])


if __name__ == "__main__":
    unittest.main()
