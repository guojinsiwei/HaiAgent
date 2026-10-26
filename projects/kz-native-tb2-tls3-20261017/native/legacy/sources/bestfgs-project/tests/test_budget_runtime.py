"""Deterministic scheduler tests: no model API, Docker, or benchmark downloads."""

import unittest
from dataclasses import replace

from bestfgs.agent import TaskRunner
from bestfgs.best_first import SemanticBestFirstGraphSearch
from bestfgs.best_first_runtime import BestFGSConfig
from bestfgs.models import (
    CommandSpec, EnvironmentSnapshot, EvidenceItem, InitialSemanticPlan, MacroAction,
    SearchGraph, SemanticDirection, StructuredContext, TaskSpec,
    TransitionAssessment, TransitionUpdate,
)
from bestfgs.rules import TaskRuleStore
from bestfgs.semantic import TaskKnowledgeBoard
from examples.demo_counter import CounterEnvironment, CounterPolicy


def action(name, *, rule_ids=()):
    return MacroAction.create(
        name=name, rationale="deterministic scheduling test",
        semantic_direction_id=name, semantic_direction_label=name,
        commands=(CommandSpec(("counter", "add", "1"), name),),
        applied_rule_ids=rule_ids,
    )


class QueuePolicy:
    def __init__(self, proposals=()):
        self.proposals = proposals
        self.calls = []

    def propose_actions(self, **kwargs):
        self.calls.append(kwargs)
        return self.proposals

    def propose_initial_plan(self, **kwargs):
        self.calls.append(kwargs)
        return InitialSemanticPlan(
            semantic_directions=tuple(SemanticDirection(f"d{i}", f"direction {i}") for i in range(4)),
            bootstrap_action=action("d0"),
        )


class StagedPolicy:
    """Two diagnostics, a partially verified repair, then a recommendation-guided finish."""
    def propose_initial_plan(self, **kwargs):
        return InitialSemanticPlan(
            semantic_directions=tuple(SemanticDirection(f"inspect{i}", f"Inspect {i}") for i in range(3)),
            bootstrap_action=self.inspect("inspect0"),
        )

    @staticmethod
    def inspect(name):
        return replace(action(name), commands=(CommandSpec(("counter", "add", "0"), "observe"),))

    def propose_actions(self, **kwargs):
        if not kwargs["solve_mode"]:
            return (self.inspect("inspect1"),)
        value = 1 if kwargs["context"].environment_summary == "value=1" else 0
        rules = tuple(rule.rule_id for rule in kwargs["rules"] if rule.kind == "recommend")
        return (replace(
            action("finish" if value else "partial", rule_ids=rules), intent="candidate",
            verification_commands=(CommandSpec(("counter", "verify", str(value + 1)), "check current step"),),
        ),)

    def update_transition(self, **kwargs):
        current_action = kwargs["action"]
        value = kwargs["outcome"].resulting_snapshot.metadata["value"]
        finished = current_action.name == "finish"
        return TransitionUpdate(
            TransitionAssessment(
                "covered" if current_action.intent == "candidate" else "exploring",
                finished, "evidence from deterministic counter",
                kwargs["task"].required_success_criteria if finished else (),
            ),
            replace(kwargs["previous"], environment_summary=f"value={value}"),
        )


class EventuallySuccessfulPolicy:
    """Advance one real step per round; optionally verify success on step four."""
    def __init__(self, succeed=True):
        self.succeed = succeed

    def propose_initial_plan(self, **kwargs):
        return InitialSemanticPlan(
            (SemanticDirection("advance", "Advance state"),), self._action(0, False)
        )

    def propose_actions(self, **kwargs):
        summary = kwargs["context"].environment_summary
        value = int(summary.split("=", 1)[1]) if summary.startswith("value=") else 0
        return (self._action(value, self.succeed and value == 3),)

    @staticmethod
    def _action(value, final):
        current = action(f"step_{value}")
        return replace(
            current,
            intent="candidate" if final else "explore",
            verification_commands=(
                (CommandSpec(("counter", "verify", "4"), "verify final value"),)
                if final else ()
            ),
        )

    def update_transition(self, **kwargs):
        value = kwargs["outcome"].resulting_snapshot.metadata["value"]
        success = kwargs["action"].intent == "candidate" and value == 4
        return TransitionUpdate(
            TransitionAssessment(
                "covered" if success else "exploring", success, "advanced state",
                kwargs["task"].required_success_criteria if success else (),
            ),
            replace(kwargs["previous"], environment_summary=f"value={value}"),
        )


class ImmediateCandidatePolicy:
    def propose_initial_plan(self, **kwargs):
        candidate = replace(
            action("finish"), intent="candidate",
            verification_commands=(CommandSpec(("counter", "verify", "1"), "verify one"),),
        )
        return InitialSemanticPlan((SemanticDirection("finish", "Finish"),), candidate)

    def propose_actions(self, **kwargs):
        return ()

    def update_transition(self, **kwargs):
        return TransitionUpdate(
            TransitionAssessment(
                "covered", True, "verified",
                kwargs["task"].required_success_criteria,
            ),
            replace(kwargs["previous"], environment_summary="value=1"),
        )


class BudgetRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.task = TaskSpec.create("inspect and repair")
        self.policy = QueuePolicy()
        self.store = TaskRuleStore(self.task.task_id)
        self.search = SemanticBestFirstGraphSearch(
            environment=CounterEnvironment(), policy=self.policy,
            rule_store=self.store, config=BestFGSConfig(),
        )
        self.graph = SearchGraph()
        self.root = self.graph.add_root(
            StructuredContext(task_goal=self.task.goal),
            EnvironmentSnapshot("root", ".", "root-files", "root"),
        )

    def child(self, parent=None, *, name="branch", exhausted=False):
        parent = parent or self.root
        child, edge, _ = self.graph.add_or_merge_child(
            parent=parent,
            context=StructuredContext(task_goal=self.task.goal, current_solution=name),
            snapshot=EnvironmentSnapshot(name, ".", f"{name}-files", name),
            action=action(name), terminal=False, semantic_coverage_rate=0,
            applicable_rule_ids=(),
        )
        child.exhausted = exhausted
        return child, edge

    def recommend(self, name, *, fingerprints=()):
        return self.store.add(
            task_id=self.task.task_id, kind="recommend",
            semantic_direction_id=name, action_name=name, evidence="real earlier evidence",
            sharing_scope="environment" if fingerprints else "task",
            applicable_environment_fingerprints=fingerprints,
        )

    def test_default_width_is_three_to_six_and_invalid_width_is_rejected(self):
        self.assertEqual(self.search.config.base_children_per_node, 3)
        self.assertEqual(self.search.config.max_children_per_node, 6)
        for width in (0, -1):
            with self.assertRaises(ValueError):
                BestFGSConfig(max_children_per_node=width).validate()
        with self.assertRaises(TypeError):
            BestFGSConfig(progressive_widening_max_children=4)
        with self.assertRaises(ValueError):
            BestFGSConfig(base_children_per_node=5, max_children_per_node=4).validate()

    def test_budget_status_exposes_remaining_resources_and_final_reserve(self):
        policy = ImmediateCandidatePolicy()
        result = TaskRunner(
            CounterEnvironment(),
            policy,
            BestFGSConfig(max_iterations=24, max_total_tool_calls=80),
        ).run(TaskSpec.create("Finish", ("Verifier passes",)))

        status = result.scheduling_trace[0]["budget_status"]
        self.assertEqual(status["remaining_iterations"], 24)
        self.assertEqual(status["remaining_total_tool_calls"], 80)
        self.assertEqual(status["reserved_final_verification_tool_calls"], 8)
        self.assertEqual(status["remaining_action_tool_calls"], 72)
        self.assertEqual(status["maximum_commands_for_next_action"], 4)
        self.assertEqual(result.final_verification_tool_calls, 1)
        self.assertLessEqual(result.total_tool_calls, 80)

    def test_initial_map_is_not_four_executable_branches(self):
        self.search._populate_actions(self.graph, self.root, self.task, initial=True)
        self.assertEqual(len(self.root.context.semantic_directions), 4)
        self.assertEqual(len(self.root.pending_actions), 1)
        self.assertEqual(len(self.graph.edges), 0)

    def test_search_records_one_phase_per_real_interaction_and_stops_on_verified_success(self):
        task = TaskSpec.create("Reach three", ("Counter equals three",))
        result = TaskRunner(
            CounterEnvironment(), CounterPolicy(),
            BestFGSConfig(
                termination_mode="legacy_verified",  # historical verified-success endpoint
                max_iterations=24, max_total_tool_calls=80,
            ),
        ).run(task)
        self.assertTrue(result.verified_success)
        self.assertLess(result.interaction_rounds, 24)
        self.assertEqual(len(result.scheduling_trace), result.interaction_rounds)
        self.assertEqual(result.scheduling_trace[0]["phase"], "initial_exploration")
        for node in result.graph.nodes.values():
            self.assertLessEqual(len(node.outgoing_edge_ids), 6)

    def test_full_episode_explores_then_repairs_then_reuses_new_recommendation(self):
        result = TaskRunner(
            CounterEnvironment(), StagedPolicy(), BestFGSConfig(
                termination_mode="legacy_verified",  # historical four-step counter episode
                experience_mode="legacy",  # phase/funnel assertions require the old recommendation mechanism
                max_iterations=8,
            ),
        ).run(TaskSpec.create("Complete both steps", ("Both steps pass",)))
        self.assertTrue(result.verified_success)
        self.assertEqual(result.interaction_rounds, 4)
        self.assertEqual(
            [item["phase"] for item in result.scheduling_trace],
            ["initial_exploration", "initial_exploration", "candidate_refinement", "recommend_exploitation"],
        )
        self.assertEqual(result.best_node.snapshot.metadata["value"], 2)
        funnel = result.post_hoc_indicators.experience_funnel
        self.assertGreaterEqual(funnel.recommend_rules_created, 1)
        self.assertGreaterEqual(funnel.recommend_rules_exposed, 1)
        self.assertEqual(funnel.recommend_actions_executed, 1)
        self.assertEqual(funnel.recommend_actions_effective, 1)

    def test_budget_extends_past_initial_limit_until_verified_success(self):
        result = TaskRunner(
            CounterEnvironment(), EventuallySuccessfulPolicy(),
            BestFGSConfig(
                termination_mode="legacy_verified",  # historical automatic success stops extension
                max_iterations=2, max_total_tool_calls=20, budget_multiplier=3,
            ),
        ).run(TaskSpec.create("Reach four", ("Counter is four",)))
        self.assertTrue(result.verified_success)
        self.assertEqual(result.interaction_rounds, 4)
        self.assertEqual(result.effective_iteration_budget, 6)
        self.assertEqual(result.hard_iteration_budget, 6)

    def test_impossible_task_stops_at_hard_iteration_limit(self):
        result = TaskRunner(
            CounterEnvironment(), EventuallySuccessfulPolicy(succeed=False),
            BestFGSConfig(
                max_iterations=2, max_total_tool_calls=20, budget_multiplier=3,
            ),
        ).run(TaskSpec.create("Never succeeds"))
        self.assertFalse(result.verified_success)
        self.assertEqual(result.interaction_rounds, 6)
        self.assertEqual(result.stop_reason, "hard_iteration_budget_exhausted")

    def test_tool_budget_also_extends_but_has_a_hard_limit(self):
        result = TaskRunner(
            CounterEnvironment(), EventuallySuccessfulPolicy(succeed=False),
            BestFGSConfig(
                max_iterations=10, max_total_tool_calls=2, budget_multiplier=3,
            ),
        ).run(TaskSpec.create("Never succeeds"))
        self.assertEqual(result.total_tool_calls, 6)
        self.assertEqual(result.stop_reason, "hard_tool_call_budget_exhausted")
        self.assertEqual(result.hard_tool_call_budget, 6)

    def test_normal_budget_stops_new_exploration_before_verification_reserve(self):
        result = TaskRunner(
            CounterEnvironment(), EventuallySuccessfulPolicy(succeed=False),
            BestFGSConfig(
                max_iterations=20,
                max_total_tool_calls=12,
            ),
        ).run(TaskSpec.create("Never succeeds"))

        self.assertFalse(result.verified_success)
        self.assertEqual(result.reserved_final_verification_tool_calls, 2)
        #最后1次普通额度不足以组成“修改+独立验证”候选，因此不再发起模型请求。
        self.assertEqual(result.total_tool_calls, 9)
        self.assertEqual(result.stop_reason, "verification_reserve_reached")

    def test_soft_tool_boundary_does_not_cut_candidate_verification_in_half(self):
        result = TaskRunner(
            CounterEnvironment(), ImmediateCandidatePolicy(),
            BestFGSConfig(
                termination_mode="legacy_verified",  # historical completion/terminal status
                max_iterations=2, max_total_tool_calls=1, budget_multiplier=4,
            ),
        ).run(TaskSpec.create("Finish", ("Verifier passes",)))
        self.assertTrue(result.verified_success)
        self.assertEqual(result.interaction_rounds, 1)
        #两次动作内调用加一次最终独立复验；最终复验现在也计入总预算。
        self.assertEqual(result.total_tool_calls, 3)
        self.assertEqual(result.final_verification_tool_calls, 1)

    def test_reusing_task_runner_does_not_transfer_memory_to_next_task(self):
        class RecordingPolicy(ImmediateCandidatePolicy):
            def __init__(self):
                self.initial_inputs = []

            def propose_initial_plan(self, **kwargs):
                self.initial_inputs.append(kwargs)
                return super().propose_initial_plan(**kwargs)

            def update_transition(self, **kwargs):
                update = super().update_transition(**kwargs)
                return replace(
                    update,
                    next_context=replace(
                        update.next_context,
                        facts_and_evidence=(EvidenceItem(
                            f"private fact for {kwargs['task'].task_id}", "current test", "yes"
                        ),),
                    ),
                )

        policy = RecordingPolicy()
        runner = TaskRunner(CounterEnvironment(), policy, BestFGSConfig(max_iterations=2))
        first_task = TaskSpec.create("First task", ("First criterion",))
        second_task = TaskSpec.create("Second task", ("Second criterion",))
        first = runner.run(first_task)
        second = runner.run(second_task)

        self.assertEqual(first.experience_mode, "conditioned")
        self.assertTrue(first.task_experiences)
        self.assertTrue(second.task_experiences)
        self.assertTrue(first.best_node.context.facts_and_evidence)
        second_input = policy.initial_inputs[1]
        self.assertEqual(second_input["rules"], ())
        self.assertEqual(second_input["context"].facts_and_evidence, ())
        self.assertEqual(second_input["context"].semantic_directions, ())
        self.assertEqual(second_input["context"].unresolved_issues, second_task.success_criteria)
        self.assertIsNot(first.graph, second.graph)
        self.assertTrue(all(record["task_id"] == first_task.task_id for record in first.task_experiences))
        self.assertTrue(all(record["task_id"] == second_task.task_id for record in second.task_experiences))
        self.assertFalse(
            {record["evidence_id"] for record in first.task_experiences}
            & {record["evidence_id"] for record in second.task_experiences}
        )


if __name__ == "__main__":
    unittest.main()
