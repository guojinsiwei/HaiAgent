import unittest

from bestfgs.metrics import INDICATOR_TIMING, PostHocIndicatorAnalyzer
from bestfgs.models import (
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
    avoid_guided: bool = False,
) -> TransitionRecord:
    command = CommandSpec(("tool", command_name), command_name)
    action = MacroAction.create(
        name=command_name,
        rationale="test",
        semantic_direction_id=direction_id,
        semantic_direction_label=direction_id,
        commands=(command,),
        applied_rule_ids=("rule",) if rule_guided else (),
        avoided_rule_ids=("avoid-rule",) if avoid_guided else (),
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
                "experience_funnel": "post_hoc",
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

    def test_knowledge_reuse_counts_recommend_and_avoid_decisions(self) -> None:
        transitions = [
            transition(
                iteration=1, parent="root", child="n1", direction_id="d1",
                command_name="reuse", before_status="unexplored",
                after_status="covered", rule_guided=True,
            ),
            transition(
                iteration=2, parent="n1", child="n2", direction_id="d2",
                command_name="safe_alternative", before_status="unexplored",
                after_status="covered", avoid_guided=True,
            ),
            transition(
                iteration=3, parent="n2", child="n3", direction_id="d3",
                command_name="plain", before_status="unexplored",
                after_status="failed",
            ),
        ]

        report = PostHocIndicatorAnalyzer.analyze(
            transitions,
            experience_events={"avoid_actions_enqueued": 1},
        )

        self.assertAlmostEqual(report.knowledge_reuse_rate, 2 / 3)
        self.assertEqual(report.rule_guided_actions, 2)
        self.assertEqual(report.experience_funnel.avoid_actions_executed, 1)
        self.assertEqual(report.experience_funnel.avoid_actions_effective, 1)
        self.assertEqual(report.experience_funnel.avoid_execution_rate, 1.0)
        self.assertEqual(report.experience_funnel.avoid_effectiveness_rate, 1.0)

    def test_experience_funnel_separates_exposure_execution_and_effect(self) -> None:
        guided = transition(
            iteration=1,
            parent="root",
            child="n1",
            direction_id="d1",
            command_name="repair",
            before_status="unexplored",
            after_status="covered",
            rule_guided=True,
        )
        report = PostHocIndicatorAnalyzer.analyze(
            [guided],
            experience_events={
                "recommend_rules_created": 2,
                "avoid_rules_created": 1,
                "retrieval_events": 3,
                "recommend_rules_exposed": 4,
                "avoid_rules_exposed": 2,
                "semantic_avoid_exposures": 1,
                "model_rule_selected_actions": 2,
                "actions_evaluated_against_rules": 5,
                "recommend_actions_validated": 2,
                "recommend_actions_enqueued": 1,
                "avoid_actions_blocked": 1,
            },
        )
        funnel = report.experience_funnel
        self.assertEqual(funnel.recommend_actions_executed, 1)
        self.assertEqual(funnel.recommend_actions_effective, 1)
        self.assertEqual(funnel.recommend_enqueue_rate, 0.5)
        self.assertEqual(funnel.recommend_execution_rate, 1.0)
        self.assertEqual(funnel.recommend_effectiveness_rate, 1.0)
        self.assertEqual(funnel.avoid_block_rate, 0.2)


if __name__ == "__main__":
    unittest.main()
