"""Offline tests for phase-adaptive semantic best-first graph search."""

import unittest
from dataclasses import replace

from cli_retrac_mcts.agent import TaskRunner
from cli_retrac_mcts.best_first import SemanticBestFirstGraphSearch, _FrontierEntry
from cli_retrac_mcts.mcts import MCTSConfig
from cli_retrac_mcts.models import (
    CommandResult,
    ExecutionOutcome,
    CommandSpec,
    InitialSemanticPlan,
    MacroAction,
    SearchGraph,
    SemanticDirection,
    StructuredContext,
    TaskSpec,
    TransitionAssessment,
    TransitionUpdate,
)
from cli_retrac_mcts.priority import (
    NodePriorityEvidence,
    calculate_priority,
    compute_solve_pressure,
    phase_weights,
)
from cli_retrac_mcts.rules import TaskRuleStore
from cli_retrac_mcts.semantic import TaskKnowledgeBoard
from examples.demo_counter import CounterEnvironment


def make_action(
    name: str,
    direction: str,
    *,
    intent: str = "explore",
    rule_ids=(),
    targets=(),
    expected_evidence: str = "",
):
    return MacroAction.create(
        name=name,
        rationale="deterministic BestFGS test",
        semantic_direction_id=direction,
        semantic_direction_label=direction,
        commands=(CommandSpec(("counter", "add", "1"), name),),
        verification_commands=(
            (CommandSpec(("counter", "verify", "1"), "verify one"),)
            if intent == "candidate"
            else ()
        ),
        intent=intent,
        applied_rule_ids=rule_ids,
        target_issue_ids=targets,
        expected_evidence=expected_evidence,
    )


class ImmediateBestFirstPolicy:
    def propose_initial_plan(self, **kwargs):
        action = make_action(
            "finish",
            "repair",
            intent="candidate",
            targets=kwargs["task"].success_criteria,
            expected_evidence="the counter equals one",
        )
        return InitialSemanticPlan(
            (SemanticDirection("repair", "repair"),),
            action,
        )

    def propose_actions(self, **kwargs):
        return ()

    def update_transition(self, **kwargs):
        return TransitionUpdate(
            TransitionAssessment(
                "covered",
                True,
                "independent counter verification passed",
                kwargs["task"].required_success_criteria,
            ),
            replace(kwargs["previous"], environment_summary="value=1"),
        )


class DistinctDirectionPolicy:
    def propose_actions(self, **kwargs):
        issue = kwargs["context"].unresolved_issues[0]
        return (
            make_action("inspect_a", "a", targets=(issue,), expected_evidence="A"),
            make_action("inspect_a_again", "a", targets=(issue,), expected_evidence="A2"),
            make_action("inspect_b", "b", targets=(issue,), expected_evidence="B"),
        )


class PriorityTests(unittest.TestCase):
    def setUp(self):
        self.context = StructuredContext(
            task_goal="repair",
            unresolved_issues=("criterion one", "criterion two"),
            semantic_directions=(
                SemanticDirection("diagnose", "diagnose", "unexplored"),
                SemanticDirection("repair", "repair", "exploring"),
            ),
        )

    def test_phase_weights_shift_from_information_to_verified_progress(self):
        early = phase_weights(0)
        late = phase_weights(1)
        self.assertAlmostEqual(
            sum((early.progress, early.recommend, early.novelty, early.information_gain, early.candidate_maturity)),
            1.0,
        )
        self.assertAlmostEqual(
            sum((late.progress, late.recommend, late.novelty, late.information_gain, late.candidate_maturity)),
            1.0,
        )
        self.assertGreater(early.novelty, late.novelty)
        self.assertGreater(early.information_gain, late.information_gain)
        self.assertGreater(late.progress, early.progress)
        self.assertGreater(late.recommend, early.recommend)

    def test_solve_pressure_is_monotonic_and_reaches_one_at_budget_boundary(self):
        early = compute_solve_pressure(
            previous=0,
            semantic_coverage=0,
            coverage_threshold=0.48,
            iteration=2,
            max_iterations=24,
            used_tool_calls=2,
            action_tool_budget=72,
        )
        late = compute_solve_pressure(
            previous=early,
            semantic_coverage=0,
            coverage_threshold=0.48,
            iteration=7,
            max_iterations=24,
            used_tool_calls=8,
            action_tool_budget=72,
        )
        self.assertGreater(early, 0)
        self.assertEqual(late, 1.0)
        self.assertEqual(
            compute_solve_pressure(
                previous=late,
                semantic_coverage=0,
                coverage_threshold=0.48,
                iteration=1,
                max_iterations=24,
                used_tool_calls=0,
                action_tool_budget=72,
            ),
            1.0,
        )

    def test_early_priority_prefers_targeted_novel_diagnosis_but_late_prefers_candidate(self):
        diagnosis = make_action(
            "diagnose",
            "diagnose",
            targets=("criterion one",),
            expected_evidence="confirm the failing path",
        )
        candidate = make_action("candidate", "repair", intent="candidate", rule_ids=("r1",))
        common = dict(
            context=self.context,
            evidence=NodePriorityEvidence(),
            direction_failures=0,
            action_repeat_count=0,
            consecutive_direction_count=0,
            max_commands_per_action=4,
            waiting_rounds=0,
        )
        early_diagnosis = calculate_priority(
            action=diagnosis, solve_pressure=0, estimated_tool_calls=1, **common
        )
        early_candidate = calculate_priority(
            action=candidate, solve_pressure=0, estimated_tool_calls=2, **common
        )
        late_diagnosis = calculate_priority(
            action=diagnosis, solve_pressure=1, estimated_tool_calls=1, **common
        )
        late_candidate = calculate_priority(
            action=candidate, solve_pressure=1, estimated_tool_calls=2, **common
        )
        self.assertGreater(early_diagnosis.score, early_candidate.score)
        self.assertGreater(late_candidate.band, late_diagnosis.band)
        self.assertGreater(late_candidate.score, late_diagnosis.score)

    def test_recommend_priority_decays_after_failures(self):
        action = make_action("repair", "repair", intent="candidate", rule_ids=("r1",))
        common = dict(
            context=self.context,
            action=action,
            evidence=NodePriorityEvidence(),
            solve_pressure=1,
            action_repeat_count=0,
            consecutive_direction_count=0,
            estimated_tool_calls=2,
            max_commands_per_action=4,
            waiting_rounds=0,
        )
        fresh = calculate_priority(direction_failures=0, **common)
        failed_twice = calculate_priority(direction_failures=2, **common)
        self.assertEqual(fresh.recommend, 1.0)
        self.assertAlmostEqual(failed_twice.recommend, 1 / 3, places=6)
        self.assertLess(failed_twice.score, fresh.score)


class BestFirstSearchTests(unittest.TestCase):
    def test_environment_failures_can_recover_without_losing_duplicate_history(self):
        class MissingToolEnvironment(CounterEnvironment):
            def execute(self, snapshot, action, max_commands):
                if action.name.startswith("probe"):
                    return ExecutionOutcome(snapshot, snapshot, action, (
                        CommandResult(action.commands[0], 127, "", "R: command not found", 0),
                    ))
                return super().execute(snapshot, action, max_commands)
        class RecoveryPolicy(ImmediateBestFirstPolicy):
            attempts = 0
            def propose_initial_plan(self, **kwargs):
                return InitialSemanticPlan((SemanticDirection("repair", "repair"),), self.propose_actions(**kwargs)[0])
            def propose_actions(self, **kwargs):
                self.attempts += 1
                if any("Runtime frontier recovery" in issue for issue in kwargs["context"].unresolved_issues):
                    return (make_action("finish", "repair", intent="candidate"),)
                return (MacroAction.create(
                    name=f"probe_{self.attempts}", rationale="locate R",
                    semantic_direction_id="repair", semantic_direction_label="repair",
                    commands=(CommandSpec((f"missing-R-{self.attempts}",), "locate R"),),
                ),)
        task = TaskSpec.create("repair environment then solve", ("counter equals one",))
        search = SemanticBestFirstGraphSearch(
            environment=MissingToolEnvironment(), policy=RecoveryPolicy(),
            rule_store=TaskRuleStore(task.task_id),
            mcts_config=MCTSConfig(max_iterations=10, max_total_tool_calls=30,
                                   base_children_per_node=3, max_children_per_node=3),
        )
        result = search.search(task=task, initial_context=StructuredContext(
            task_goal=task.goal, unresolved_issues=task.required_success_criteria,
        ))
        self.assertTrue(result.succeeded)
        self.assertEqual(result.interaction_rounds, 4)
        self.assertEqual(search._empty_frontier_recoveries, 1)
        root = result.graph.root()
        self.assertEqual(len(root.tried_action_ids), 4)
        self.assertLessEqual(len(search._capacity_action_ids(root)), 3)

    def test_empty_generation_has_bounded_recovery_and_does_not_increase_budgets(self):
        class EmptyPolicy:
            calls = 0
            def propose_initial_skeleton(self, **kwargs):
                return ()
            def propose_actions(self, **kwargs):
                self.calls += 1
                return ()
        task = TaskSpec.create("empty generator")
        policy = EmptyPolicy()
        search = SemanticBestFirstGraphSearch(
            environment=CounterEnvironment(), policy=policy,
            rule_store=TaskRuleStore(task.task_id),
            mcts_config=MCTSConfig(max_iterations=24, max_total_tool_calls=80,
                                   base_children_per_node=3, max_children_per_node=3),
        )
        result = search.search(task=task, initial_context=StructuredContext(task_goal=task.goal))
        self.assertFalse(result.succeeded)
        self.assertEqual(result.stop_reason, "search_exhausted")
        self.assertEqual(search._empty_frontier_recoveries, 2)
        self.assertLessEqual(policy.calls, 4)
        self.assertEqual(result.total_tool_calls, 0)

    def _search_for_pruning(self, task, context, **config_overrides):
        config = MCTSConfig(expansion_width=3, **config_overrides)
        search = SemanticBestFirstGraphSearch(
            environment=CounterEnvironment(),
            policy=DistinctDirectionPolicy(),
            rule_store=TaskRuleStore(task.task_id),
            mcts_config=config,
        )
        graph = SearchGraph()
        root = graph.add_root(context, search.environment.initial_snapshot())
        search._knowledge_board = TaskKnowledgeBoard.create(
            root.snapshot.fingerprint,
            context,
        )
        return search, graph, root

    def _frontier_choice(self, *, solve_pressure: float) -> str:
        task = TaskSpec.create(
            "repair",
            ("criterion one", "criterion two"),
        )
        context = StructuredContext(
            task_goal=task.goal,
            unresolved_issues=task.required_success_criteria,
            semantic_directions=(
                SemanticDirection("diagnose", "diagnose", "unexplored"),
                SemanticDirection("repair", "repair", "exploring"),
            ),
        )
        store = TaskRuleStore(task.task_id)
        rule = store.add(
            task_id=task.task_id,
            kind="recommend",
            semantic_direction_id="repair",
            action_name="candidate",
            evidence="a previous transition supported this repair",
        )
        search = SemanticBestFirstGraphSearch(
            environment=CounterEnvironment(),
            policy=DistinctDirectionPolicy(),
            rule_store=store,
            mcts_config=MCTSConfig(expansion_width=3),
        )
        graph = SearchGraph()
        root = graph.add_root(context, search.environment.initial_snapshot())
        search._knowledge_board = TaskKnowledgeBoard.create(
            root.snapshot.fingerprint,
            context,
        )
        root.pending_actions.extend(
            (
                make_action(
                    "diagnose",
                    "diagnose",
                    targets=("criterion one",),
                    expected_evidence="confirm the failing path",
                ),
                make_action(
                    "candidate",
                    "repair",
                    intent="candidate",
                    rule_ids=(rule.rule_id,),
                ),
            )
        )
        search._solve_pressure = solve_pressure
        selected_node, _ = search._select(graph, task, iteration=1)
        self.assertIs(selected_node, root)
        selected_action = search._take_pending_action(root)
        self.assertIsNotNone(selected_action)
        return selected_action.name

    def test_global_frontier_changes_preference_between_phases(self):
        self.assertEqual(self._frontier_choice(solve_pressure=0.0), "diagnose")
        self.assertEqual(self._frontier_choice(solve_pressure=1.0), "candidate")

    def test_task_runner_uses_best_first_and_stops_on_verified_success(self):
        result = TaskRunner(
            CounterEnvironment(),
            ImmediateBestFirstPolicy(),
            MCTSConfig(max_iterations=24, max_total_tool_calls=80),
        ).run(TaskSpec.create("make the counter one"))
        self.assertEqual(result.search_algorithm, "phase_adaptive_semantic_best_first")
        self.assertTrue(result.verified_success)
        self.assertEqual(result.interaction_rounds, 1)
        self.assertLess(result.interaction_rounds, 24)
        self.assertEqual(result.scheduling_trace[0]["search_algorithm"], result.search_algorithm)
        self.assertIn("priority", result.scheduling_trace[0])

    def test_early_frontier_keeps_distinct_directions_without_beam_execution(self):
        task = TaskSpec.create("inspect two directions")
        context = StructuredContext(
            task_goal=task.goal,
            unresolved_issues=task.required_success_criteria,
            semantic_directions=(
                SemanticDirection("a", "a"),
                SemanticDirection("b", "b"),
            ),
        )
        search = SemanticBestFirstGraphSearch(
            environment=CounterEnvironment(),
            policy=DistinctDirectionPolicy(),
            rule_store=TaskRuleStore(task.task_id),
            mcts_config=MCTSConfig(expansion_width=3),
        )
        graph = SearchGraph()
        root = graph.add_root(context, search.environment.initial_snapshot())
        search._knowledge_board = TaskKnowledgeBoard.create(root.snapshot.fingerprint, context)
        search._populate_actions(graph, root, task, initial=False)
        self.assertEqual(
            {item.semantic_direction_id for item in root.pending_actions},
            {"a", "b"},
        )
        self.assertEqual(len(root.pending_actions), 2)

    def test_best_first_does_not_backpropagate_ucb_visits(self):
        task = TaskSpec.create("no ucb")
        context = StructuredContext(task_goal=task.goal)
        graph = SearchGraph()
        root = graph.add_root(context, CounterEnvironment().initial_snapshot())
        SemanticBestFirstGraphSearch._backpropagate(graph, [], 1.0)
        self.assertEqual(root.visits, 0)
        self.assertEqual(root.total_value, 0.0)

    def test_frontier_keeps_at_most_two_entries_per_direction_globally(self):
        task = TaskSpec.create("inspect one direction")
        context = StructuredContext(
            task_goal=task.goal,
            unresolved_issues=task.required_success_criteria,
            semantic_directions=(SemanticDirection("same", "same"),),
        )
        search, graph, root = self._search_for_pruning(task, context)
        root.pending_actions.extend(
            make_action(
                f"same_{index}",
                "same",
                expected_evidence=f"evidence {index}",
            )
            for index in range(4)
        )

        selected, _ = search._select(graph, task, iteration=1)

        self.assertIs(selected, root)
        self.assertEqual(search._frontier_raw_size, 4)
        self.assertEqual(search._frontier_size, 2)
        self.assertEqual(search._frontier_pruned_direction_quota, 2)

    def test_stale_direction_is_suspended_while_fresh_direction_exists(self):
        task = TaskSpec.create("prefer fresh evidence")
        context = StructuredContext(
            task_goal=task.goal,
            unresolved_issues=task.required_success_criteria,
            semantic_directions=(
                SemanticDirection("stale", "stale"),
                SemanticDirection("fresh", "fresh"),
            ),
        )
        search, graph, root = self._search_for_pruning(task, context)
        root.pending_actions.extend(
            (
                make_action("old", "stale", expected_evidence="old evidence"),
                make_action("new", "fresh", expected_evidence="new evidence"),
            )
        )
        search._direction_attempts["stale"] = 2
        search._direction_last_evidence_iteration["stale"] = 1

        selected, _ = search._select(graph, task, iteration=5)
        action = search._take_pending_action(selected)

        self.assertEqual(action.semantic_direction_id, "fresh")
        self.assertEqual(search._frontier_pruned_stale, 1)

    def test_stale_entry_is_reactivated_when_it_is_the_only_choice(self):
        task = TaskSpec.create("recover soft-pruned direction")
        context = StructuredContext(
            task_goal=task.goal,
            unresolved_issues=task.required_success_criteria,
            semantic_directions=(SemanticDirection("stale", "stale"),),
        )
        search, graph, root = self._search_for_pruning(task, context)
        root.pending_actions.append(
            make_action("old", "stale", expected_evidence="old evidence")
        )
        search._direction_attempts["stale"] = 2
        search._direction_last_evidence_iteration["stale"] = 1

        selected, _ = search._select(graph, task, iteration=5)

        self.assertIs(selected, root)
        self.assertEqual(search._frontier_reactivated, 1)

    def test_dominated_frontier_entry_is_suppressed(self):
        task = TaskSpec.create("remove dominated candidate")
        context = StructuredContext(task_goal=task.goal)
        search, _, _ = self._search_for_pruning(task, context)
        strong_priority = calculate_priority(
            context=context,
            action=make_action("strong", "repair", intent="candidate"),
            evidence=NodePriorityEvidence(real_progress=1.0, candidate_maturity=1.0),
            solve_pressure=1.0,
            direction_failures=0,
            action_repeat_count=0,
            consecutive_direction_count=0,
            estimated_tool_calls=1,
            max_commands_per_action=4,
            waiting_rounds=0,
        )
        weak_priority = replace(
            strong_priority,
            score=strong_priority.score - 0.1,
            progress=0.5,
            candidate_maturity=0.5,
            cost_penalty=strong_priority.cost_penalty + 0.05,
        )
        strong = _FrontierEntry(
            "action", "strong-node", "strong-action", "repair", strong_priority, 1
        )
        weak = _FrontierEntry(
            "action", "weak-node", "weak-action", "repair", weak_priority, 1
        )

        active = search._prune_frontier_entries([strong, weak], iteration=1)

        self.assertEqual(active, [strong])
        self.assertEqual(search._frontier_pruned_dominated, 1)


if __name__ == "__main__":
    unittest.main()
