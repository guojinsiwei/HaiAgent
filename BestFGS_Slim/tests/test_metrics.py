import unittest

from cli_retrac_mcts.metrics import INDICATOR_TIMING, PostHocIndicatorAnalyzer
from cli_retrac_mcts.models import (
    CommandResult,
    CommandSpec,
    EnvironmentSnapshot,
    ExecutionOutcome,
    MacroAction,
    RewardBreakdown,
    SemanticDirection,
    StructuredContext,
    TransitionAssessment,
    TransitionRecord,
)


def context(direction_id: str, status: str) -> StructuredContext:
    return StructuredContext(
        task_goal="test",
        semantic_directions=(SemanticDirection(direction_id, direction_id, status),),
    )


def transition(
    *,
    iteration: int,
    parent: str,
    child: str,
    direction_id: str,
    command_name: str,
    before_status: str,
    after_status: str,
    success: bool = False,
    rule_guided: bool = False,
) -> TransitionRecord:
    command = CommandSpec(("tool", command_name), command_name)
    action = MacroAction.create(
        name=command_name,
        rationale="test",
        semantic_direction_id=direction_id,
        semantic_direction_label=direction_id,
        commands=(command,),
        applied_rule_ids=("rule",) if rule_guided else (),
    )
    parent_snapshot = EnvironmentSnapshot("s0", ".", "s0", "parent")
    child_snapshot = EnvironmentSnapshot(f"s{iteration}", ".", f"s{iteration}", "child")
    outcome = ExecutionOutcome(
        parent_snapshot,
        child_snapshot,
        action,
        (CommandResult(command, 0, "", "", 0.0),),
    )
    before = context(direction_id, before_status)
    after = context(direction_id, after_status)
    return TransitionRecord(
        task_id="task",
        iteration=iteration,
        parent_node_id=parent,
        child_node_id=child,
        action=action,
        outcome=outcome,
        assessment=TransitionAssessment(after_status, success, "test"),
        reward=RewardBreakdown(0.0, 0.0, 0.0),
        state_before=before,
        state_after=after,
        semantic_coverage_before=1.0 if before_status == "covered" else 0.0,
        semantic_coverage_after=1.0 if after_status == "covered" else 0.0,
    )


class IndicatorTests(unittest.TestCase):
    def test_only_semantic_coverage_is_online(self) -> None:
        self.assertEqual(
            INDICATOR_TIMING,
            {
                "semantic_coverage_rate": "online",
                "effective_exploration_ratio": "post_hoc",
                "knowledge_reuse_rate": "post_hoc",
                "tool_call_redundancy_rate": "post_hoc",
            },
        )

    def test_three_post_hoc_indicators_use_complete_trajectory(self) -> None:
        transitions = [
            transition(
                iteration=1,
                parent="root",
                child="n1",
                direction_id="d1",
                command_name="inspect",
                before_status="exploring",
                after_status="covered",
            ),
            transition(
                iteration=2,
                parent="root",
                child="n2",
                direction_id="d2",
                command_name="probe",
                before_status="unexplored",
                after_status="failed",
                rule_guided=True,
            ),
            transition(
                iteration=3,
                parent="n1",
                child="n3",
                direction_id="d1",
                command_name="inspect",
                before_status="covered",
                after_status="covered",
                success=True,
                rule_guided=True,
            ),
        ]
        report = PostHocIndicatorAnalyzer.analyze(transitions)
        self.assertEqual(report.effective_exploration_ratio, 0.5)
        self.assertAlmostEqual(report.knowledge_reuse_rate, 2 / 3)
        self.assertAlmostEqual(report.tool_call_redundancy_rate, 1 / 3)

    def test_knowledge_reuse_counts_rule_guided_share_even_when_task_fails(self) -> None:
        transitions = [
            transition(
                iteration=1,
                parent="root",
                child="n1",
                direction_id="d1",
                command_name="inspect",
                before_status="unexplored",
                after_status="exploring",
                rule_guided=True,
            ),
            transition(
                iteration=2,
                parent="root",
                child="n2",
                direction_id="d2",
                command_name="test",
                before_status="unexplored",
                after_status="failed",
            ),
        ]

        report = PostHocIndicatorAnalyzer.analyze(transitions)

        self.assertFalse(any(item.assessment.task_success for item in transitions))
        self.assertEqual(report.rule_guided_actions, 1)
        self.assertEqual(report.knowledge_reuse_rate, 0.5)


if __name__ == "__main__":
    unittest.main()
