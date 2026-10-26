import unittest
from dataclasses import replace

from bestfgs.models import (
    CommandSpec,
    MacroAction,
    SemanticDirection,
    StructuredContext,
)
from bestfgs.rules import TaskRuleStore


def make_action(
    name: str,
    *,
    direction_id: str = "direction-a",
    direction_label: str = "Direction A",
    applied_rule_ids: tuple[str, ...] = (),
) -> MacroAction:
    return MacroAction.create(
        name=name,
        rationale="test",
        semantic_direction_id=direction_id,
        semantic_direction_label=direction_label,
        commands=(CommandSpec(("tool", name), "test command"),),
        applied_rule_ids=applied_rule_ids,
    )


class TaskRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = TaskRuleStore(task_id="task-a")

    def test_rules_are_task_scoped(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add(
                task_id="task-b",
                kind="recommend",
                semantic_direction_id="direction-a",
                action_name="inspect",
                evidence="test",
            )
        with self.assertRaises(ValueError):
            self.store.retrieve(
                task_id="task-b", context=StructuredContext(task_goal="other task"), limit=5,
            )
        with self.assertRaises(ValueError):
            self.store.apply(task_id="task-b", action=make_action("inspect"))

    def test_recommend_and_avoid_rules_are_applied_by_semantic_direction(self) -> None:
        recommended = self.store.add(
            task_id="task-a",
            kind="recommend",
            semantic_direction_id="direction-a",
            action_name="inspect",
            evidence="worked",
        )
        repeated = make_action("repeat")
        self.store.add(
            task_id="task-a",
            kind="avoid",
            semantic_direction_id="direction-a",
            action_name="repeat",
            evidence="failed",
            failure_kind="duplicate_action",
            scope="exact_action",
            action_signature=repeated.signature(),
        )
        blocked, applied = self.store.apply(task_id="task-a", action=make_action("inspect"))
        self.assertFalse(blocked)
        self.assertEqual(applied, (recommended.rule_id,))
        blocked, _ = self.store.apply(task_id="task-a", action=repeated)
        self.assertTrue(blocked)

        context = StructuredContext(
            task_goal="test",
            semantic_directions=(SemanticDirection("direction-a", "Direction A"),),
        )
        self.assertEqual(len(self.store.relevant(task_id="task-a", context=context)), 2)

    def test_top_k_retrieval_uses_semantic_summary_not_only_direction_id(self) -> None:
        relevant = self.store.add(
            task_id="task-a",
            kind="recommend",
            semantic_direction_id="inspect_old_tests",
            action_name="read_test_cases",
            evidence="读取测试帮助定位了失败断言",
            semantic_direction_label="测试失败定位",
            condition="需要检查单元测试失败原因",
            guidance="先阅读相关测试并运行失败用例",
        )
        self.store.add(
            task_id="task-a",
            kind="recommend",
            semantic_direction_id="install_dependencies",
            action_name="install_packages",
            evidence="依赖安装成功",
            semantic_direction_label="依赖安装",
            condition="项目缺少第三方依赖",
            guidance="安装项目依赖包",
        )
        context = StructuredContext(
            task_goal="修复单元测试失败",
            unresolved_issues=("尚未定位测试失败原因",),
            semantic_directions=(
                SemanticDirection("analyze_test_failures", "分析测试失败"),
            ),
        )

        retrieved = self.store.retrieve(
            task_id="task-a",
            context=context,
            limit=1,
        )

        self.assertEqual(retrieved, (relevant,))

    def test_model_selected_semantic_rule_is_validated_and_applied(self) -> None:
        recommended = self.store.add(
            task_id="task-a",
            kind="recommend",
            semantic_direction_id="old-test-direction",
            action_name="old-test-action",
            evidence="worked before",
            condition="tests are failing",
            guidance="inspect the failing assertion",
        )
        action = make_action(
            "analyze_failure",
            direction_id="new-test-direction",
            applied_rule_ids=(recommended.rule_id, "hallucinated-rule"),
        )

        blocked, applied = self.store.apply(task_id="task-a", action=action)

        self.assertFalse(blocked)
        self.assertEqual(applied, (recommended.rule_id,))

    def test_semantic_avoid_remains_guidance_even_when_model_selects_it(self) -> None:
        avoided = self.store.add(
            task_id="task-a",
            kind="avoid",
            semantic_direction_id="direction-a",
            action_name="repeat",
            evidence="failed in the previous state",
            condition="the file did not exist before repair",
            guidance="do not repeat the missing-file command",
        )

        blocked_without_confirmation, _ = self.store.apply(
            task_id="task-a",
            action=make_action("repeat"),
        )
        blocked_with_confirmation, _ = self.store.apply(
            task_id="task-a",
            action=make_action("different-name", applied_rule_ids=(avoided.rule_id,)),
        )

        self.assertFalse(blocked_without_confirmation)
        self.assertFalse(blocked_with_confirmation)

        alternative = make_action("different-name")
        alternative = replace(
            alternative,
            avoided_rule_ids=(avoided.rule_id,),
        )
        decision = self.store.evaluate(task_id="task-a", action=alternative)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.recommend_rule_ids, ())
        self.assertEqual(decision.avoided_rule_ids, (avoided.rule_id,))

        unrelated = make_action("different-name", direction_id="unrelated-direction")
        unrelated = replace(
            unrelated,
            rationale="inspect an unrelated subsystem",
            semantic_direction_label="unrelated subsystem",
            avoided_rule_ids=(avoided.rule_id,),
        )
        unrelated_decision = self.store.evaluate(
            task_id="task-a", action=unrelated,
        )
        self.assertEqual(unrelated_decision.avoided_rule_ids, ())

    def test_command_failure_does_not_block_new_action_in_same_direction(self) -> None:
        failed_action = make_action("bad-command")
        avoided = self.store.add(
            task_id="task-a",
            kind="avoid",
            semantic_direction_id="direction-a",
            action_name=failed_action.name,
            evidence="SyntaxError: unexpected token",
            failure_kind="command_syntax",
            scope="exact_command",
            command_signatures=(failed_action.commands[0].normalized(),),
        )

        fixed_action = make_action(
            "fixed-command",
            applied_rule_ids=(avoided.rule_id,),
        )
        repeated_action = make_action(
            "bad-command",
            applied_rule_ids=(avoided.rule_id,),
        )
        renamed_repeat = MacroAction.create(
            name="renamed-repeat",
            rationale="same bad command under a new name",
            semantic_direction_id="different-direction",
            semantic_direction_label="Different direction",
            commands=failed_action.commands,
        )

        self.assertFalse(self.store.apply(task_id="task-a", action=fixed_action)[0])
        self.assertTrue(self.store.apply(task_id="task-a", action=repeated_action)[0])
        self.assertTrue(self.store.apply(task_id="task-a", action=renamed_repeat)[0])

    def test_exact_action_rule_does_not_block_a_different_action(self) -> None:
        covered_action = make_action("read-once")
        avoided = self.store.add(
            task_id="task-a",
            kind="avoid",
            semantic_direction_id="direction-a",
            action_name=covered_action.name,
            evidence="already covered",
            failure_kind="duplicate_action",
            scope="exact_action",
            action_signature=covered_action.signature(),
        )

        different = make_action(
            "implement-solution",
            applied_rule_ids=(avoided.rule_id,),
        )

        self.assertTrue(self.store.apply(task_id="task-a", action=covered_action)[0])
        self.assertFalse(self.store.apply(task_id="task-a", action=different)[0])

    def test_environment_scoped_experience_only_reaches_equivalent_branches(self) -> None:
        failed_action = make_action("state-specific-failure")
        rule = self.store.add(
            task_id="task-a",
            kind="avoid",
            semantic_direction_id="direction-a",
            action_name=failed_action.name,
            evidence="failed only on this candidate state",
            failure_kind="path_error",
            scope="exact_command",
            command_signatures=(failed_action.commands[0].normalized(),),
            sharing_scope="environment",
            applicable_environment_fingerprints=("same-files",),
        )
        context = StructuredContext(
            task_goal="test",
            semantic_directions=(SemanticDirection("direction-a", "Direction A"),),
        )

        same_state = self.store.retrieve(
            task_id="task-a",
            context=context,
            limit=5,
            environment_fingerprint="same-files",
        )
        different_state = self.store.retrieve(
            task_id="task-a",
            context=context,
            limit=5,
            environment_fingerprint="different-files",
        )

        self.assertIn(rule, same_state)
        self.assertNotIn(rule, different_state)
        self.assertTrue(
            self.store.apply(
                task_id="task-a",
                action=failed_action,
                environment_fingerprint="same-files",
            )[0]
        )
        self.assertFalse(
            self.store.apply(
                task_id="task-a",
                action=failed_action,
                environment_fingerprint="different-files",
            )[0]
        )

    def test_portable_tool_failure_is_recalled_across_directions(self) -> None:
        rule = self.store.add(
            task_id="task-a",
            kind="avoid",
            semantic_direction_id="old-build-direction",
            action_name="use_missing_tool",
            evidence="tool-x: command not found",
            failure_kind="tool_missing",
            scope="exact_command",
            command_signatures=("tool-x --version",),
            sharing_scope="task",
        )
        unrelated_context = StructuredContext(
            task_goal="repair parser behavior",
            semantic_directions=(
                SemanticDirection("inspect_parser", "Inspect parser"),
            ),
        )

        retrieved = self.store.retrieve(
            task_id="task-a",
            context=unrelated_context,
            limit=5,
            environment_fingerprint="any-files",
        )

        self.assertIn(rule, retrieved)


if __name__ == "__main__":
    unittest.main()
