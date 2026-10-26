import json
import tempfile
import unittest
from dataclasses import dataclass, field, replace
from pathlib import Path

from cli_retrac_mcts.agent import TaskRunner
from cli_retrac_mcts.mcts import (
    CoverageGuidedMCTS,
    MCTSConfig,
    adapt_search_budget,
)
from cli_retrac_mcts.models import (
    CommandResult,
    CommandSpec,
    EnvironmentSnapshot,
    EvidenceItem,
    ExecutionOutcome,
    MacroAction,
    ModelCallError,
    SearchEdge,
    SearchGraph,
    SearchNode,
    SemanticDirection,
    StructuredContext,
    TaskSpec,
    TransitionAssessment,
    TransitionUpdate,
)
from cli_retrac_mcts.rules import TaskRuleStore
from cli_retrac_mcts.semantic import TaskKnowledgeBoard
from examples.demo_counter import CounterEnvironment, run_demo


@dataclass(slots=True)
class CoveredDirectionPolicy:
    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (self._action("inspect", "inspect_requirements", 1),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        return (
            self._action("repeat_inspection", "inspect_requirements", 1),
            self._action(
                "repair_and_test",
                "repair_implementation",
                2,
                candidate=True,
                expected_value=3,
            ),
        )

    def update_transition(self, **kwargs) -> TransitionUpdate:
        action = kwargs["action"]
        success = action.semantic_direction_id == "repair_implementation"
        value = kwargs["outcome"].resulting_snapshot.metadata["value"]
        return TransitionUpdate(
            TransitionAssessment(
                "covered",
                success,
                f"covered {action.semantic_direction_id}",
                kwargs["task"].required_success_criteria if success else (),
            ),
            replace(kwargs["previous"], environment_summary=f"value={value}"),
        )

    @staticmethod
    def _action(
        name: str,
        direction: str,
        delta: int,
        *,
        candidate: bool = False,
        expected_value: int = 3,
    ) -> MacroAction:
        return MacroAction.create(
            name=name,
            rationale="test semantic filtering",
            semantic_direction_id=direction,
            semantic_direction_label=direction,
            commands=(CommandSpec(("counter", "add", str(delta)), name),),
            verification_commands=(
                CommandSpec(
                    ("counter", "verify", str(expected_value)),
                    f"verify counter equals {expected_value}",
                ),
            ) if candidate else (),
            intent="candidate" if candidate else "explore",
        )


@dataclass(slots=True)
class UnverifiedSuccessPolicy(CoveredDirectionPolicy):
    """Model claims success, but the proposed action has no independent verifier."""

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        return (
            self._action("repair_without_test", "repair_implementation", 2),
        )


@dataclass(slots=True)
class ForgetfulFactsPolicy:
    """Simulate a model that omits an earlier verified fact during compression."""

    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (CoveredDirectionPolicy._action("first", "first_direction", 1),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        return (CoveredDirectionPolicy._action("second", "second_direction", 1),)

    def update_transition(self, **kwargs) -> TransitionUpdate:
        if kwargs["action"].name == "first":
            context = StructuredContext(
                task_goal=kwargs["task"].goal,
                facts_and_evidence=(
                    EvidenceItem("Stable fact", "first command", "yes"),
                ),
            )
        else:
            context = StructuredContext(task_goal=kwargs["task"].goal)
        return TransitionUpdate(
            TransitionAssessment("covered", False, "direction covered"),
            context,
        )


@dataclass(slots=True)
class FailingActionPolicy:
    update_calls: int = 0

    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (CoveredDirectionPolicy._action("failing_command", "inspect_failure", 1),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        return ()

    def update_transition(self, **kwargs) -> TransitionUpdate:
        self.update_calls += 1
        raise AssertionError("failed CLI transitions must not call the model policy")


class FailingCounterEnvironment(CounterEnvironment):
    def execute(self, snapshot, action, max_commands) -> ExecutionOutcome:
        command = action.commands[0]
        result = CommandResult(
            command=command,
            return_code=2,
            stdout="",
            stderr="simulated command failure",
            duration_seconds=0.0,
        )
        return ExecutionOutcome(snapshot, snapshot, action, (result,))


@dataclass(slots=True)
class UnavailableTransitionPolicy:
    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (CoveredDirectionPolicy._action("successful_cli", "inspect_output", 1),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        return ()

    def update_transition(self, **kwargs) -> TransitionUpdate:
        raise ModelCallError("temporary model outage")


@dataclass(slots=True)
class UnavailableInitialPolicy:
    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        raise ModelCallError("initial model outage")

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        return ()

    def update_transition(self, **kwargs) -> TransitionUpdate:
        raise AssertionError("no transition should run")


@dataclass(slots=True)
class AllAvoidedPolicy:
    avoid_rule_id: str

    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        action = CoveredDirectionPolicy._action(
            "implement_fallback",
            "blocked_implementation",
            1,
            candidate=True,
            expected_value=1,
        )
        return (replace(action, applied_rule_ids=(self.avoid_rule_id,)),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        raise AssertionError("the retained fallback must avoid another model expansion")

    def update_transition(self, **kwargs) -> TransitionUpdate:
        return TransitionUpdate(
            TransitionAssessment(
                "covered",
                True,
                "fallback action executed",
                kwargs["task"].required_success_criteria,
            ),
            kwargs["previous"],
        )


@dataclass(slots=True)
class OneBrokenBranchPolicy:
    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (
            CoveredDirectionPolicy._action("branch_a", "branch_a", 1),
            CoveredDirectionPolicy._action("branch_b", "branch_b", 2),
        )

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        if kwargs["context"].environment_summary == "value=1":
            raise ModelCallError("branch A expansion outage")
        if not kwargs["context"].environment_summary:
            return (CoveredDirectionPolicy._action("branch_b", "branch_b", 2),)
        return (
            CoveredDirectionPolicy._action(
                "repair",
                "repair",
                1,
                candidate=True,
                expected_value=3,
            ),
        )

    def update_transition(self, **kwargs) -> TransitionUpdate:
        value = kwargs["outcome"].resulting_snapshot.metadata["value"]
        success = kwargs["action"].name == "repair" and value == 3
        assessment = TransitionAssessment(
            "covered" if success else "exploring",
            success,
            "target reached" if success else "branch explored",
            kwargs["task"].required_success_criteria if success else (),
        )
        context = replace(kwargs["previous"], environment_summary=f"value={value}")
        return TransitionUpdate(assessment, context)


@dataclass(slots=True)
class ReadThenSolveEnvironment:
    snapshot_index: int = 0

    def initial_snapshot(self) -> EnvironmentSnapshot:
        return EnvironmentSnapshot("phase-root", "phase://root", "root-files", "root")

    def restore(self, snapshot: EnvironmentSnapshot) -> EnvironmentSnapshot:
        return snapshot

    def execute(self, snapshot, action, max_commands) -> ExecutionOutcome:
        self.snapshot_index += 1
        fingerprint = {
            "inspect": snapshot.fingerprint,
            "edit": "draft-files",
            "fix_and_test": "fixed-files",
            "corrupt": "corrupt-files",
        }[action.name]
        resulting = EnvironmentSnapshot(
            f"phase-{self.snapshot_index}",
            f"phase://{self.snapshot_index}",
            fingerprint,
            action.name,
        )
        result = CommandResult(action.commands[0], 0, action.name, "", 0.0)
        remaining = max(0, max_commands - 1)
        functional_results = self.verify(
            resulting,
            action.verification_commands[:remaining],
        )
        return ExecutionOutcome(
            snapshot,
            resulting,
            action,
            (result,),
            functional_validation_results=functional_results,
        )

    def verify(
        self,
        snapshot: EnvironmentSnapshot,
        commands: tuple[CommandSpec, ...],
    ) -> tuple[CommandResult, ...]:
        results: list[CommandResult] = []
        for command in commands:
            expected = command.argv[-1]
            succeeded = snapshot.fingerprint == expected
            results.append(
                CommandResult(
                    command,
                    0 if succeeded else 1,
                    snapshot.fingerprint,
                    "" if succeeded else f"expected {expected}",
                    0.0,
                )
            )
        return tuple(results)


@dataclass(slots=True)
class LatestCandidateFailsReverifyEnvironment(ReadThenSolveEnvironment):
    verification_counts: dict[str, int] = field(default_factory=dict)

    def verify(
        self,
        snapshot: EnvironmentSnapshot,
        commands: tuple[CommandSpec, ...],
    ) -> tuple[CommandResult, ...]:
        results = ReadThenSolveEnvironment.verify(self, snapshot, commands)
        fingerprint = snapshot.fingerprint
        self.verification_counts[fingerprint] = (
            self.verification_counts.get(fingerprint, 0) + 1
        )
        if fingerprint == "fixed-files" and self.verification_counts[fingerprint] > 1:
            command = commands[0]
            return (
                CommandResult(
                    command,
                    1,
                    "",
                    "simulated final-only regression",
                    0.0,
                ),
            )
        return results


@dataclass(slots=True)
class ReadThenSolvePolicy:
    solve_flags: list[bool] = field(default_factory=list)
    saw_shared_fact: bool = False

    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (self._action("inspect", "understand_source"),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        solve_mode = kwargs.get("solve_mode", False)
        self.solve_flags.append(solve_mode)
        self.saw_shared_fact = self.saw_shared_fact or any(
            item.claim == "Shared source fact"
            for item in kwargs["context"].facts_and_evidence
        )
        if kwargs["context"].current_solution == "draft":
            return (self._action("fix_and_test", "implement_solution"),)
        return (self._action("edit", "implement_solution"),)

    def update_transition(self, **kwargs) -> TransitionUpdate:
        action = kwargs["action"]
        if action.name == "inspect":
            context = replace(
                kwargs["previous"],
                facts_and_evidence=(
                    EvidenceItem("Shared source fact", "inspect output", "yes"),
                ),
                environment_summary="source understood",
            )
            return TransitionUpdate(
                TransitionAssessment("covered", False, "source understood"),
                context,
            )
        if action.name == "edit":
            return TransitionUpdate(
                TransitionAssessment(
                    "exploring",
                    False,
                    "draft written",
                    kwargs["task"].required_success_criteria,
                ),
                replace(
                    kwargs["previous"],
                    current_solution="draft",
                    environment_summary="draft written",
                ),
            )
        return TransitionUpdate(
            TransitionAssessment(
                "covered",
                True,
                "tests passed",
                kwargs["task"].required_success_criteria,
            ),
            replace(
                kwargs["previous"],
                current_solution="fixed",
                environment_summary="tests passed",
            ),
        )

    @staticmethod
    def _action(name: str, direction: str) -> MacroAction:
        candidate_fingerprints = {
            "edit": "draft-files",
            "fix_and_test": "fixed-files",
        }
        expected_fingerprint = candidate_fingerprints.get(name)
        return MacroAction.create(
            name=name,
            rationale="phase test",
            semantic_direction_id=direction,
            semantic_direction_label=direction,
            commands=(CommandSpec(("tool", name), name),),
            verification_commands=(
                CommandSpec(
                    ("verify", expected_fingerprint),
                    f"verify {expected_fingerprint}",
                ),
            ) if expected_fingerprint else (),
            intent="candidate" if expected_fingerprint else "explore",
            expected_effect=name,
        )


@dataclass(slots=True)
class RegressingSolutionPolicy:
    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (ReadThenSolvePolicy._action("inspect", "understand_source"),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        name = "corrupt" if kwargs["context"].current_solution == "draft" else "edit"
        return (ReadThenSolvePolicy._action(name, "implement_solution"),)

    def update_transition(self, **kwargs) -> TransitionUpdate:
        action = kwargs["action"]
        if action.name == "inspect":
            return TransitionUpdate(
                TransitionAssessment("covered", False, "source understood"),
                replace(
                    kwargs["previous"],
                    facts_and_evidence=(
                        EvidenceItem("Shared source fact", "inspect output", "yes"),
                    ),
                ),
            )
        if action.name == "edit":
            return TransitionUpdate(
                TransitionAssessment("exploring", False, "working draft"),
                replace(kwargs["previous"], current_solution="draft"),
            )
        return TransitionUpdate(
            TransitionAssessment("failed", False, "regression detected"),
            replace(kwargs["previous"], current_solution="corrupt"),
        )


@dataclass(slots=True)
class SolveFailurePolicy:
    failure_updates: int = 0

    def propose_initial_skeleton(self, **kwargs) -> tuple[MacroAction, ...]:
        return (ReadThenSolvePolicy._action("inspect", "understand_source"),)

    def propose_actions(self, **kwargs) -> tuple[MacroAction, ...]:
        return (ReadThenSolvePolicy._action("edit_and_test", "implement_solution"),)

    def update_transition(self, **kwargs) -> TransitionUpdate:
        if kwargs["action"].name == "inspect":
            return TransitionUpdate(
                TransitionAssessment("covered", False, "source understood"),
                replace(
                    kwargs["previous"],
                    facts_and_evidence=(
                        EvidenceItem("Shared source fact", "inspect output", "yes"),
                    ),
                ),
            )
        self.failure_updates += 1
        return TransitionUpdate(
            TransitionAssessment("exploring", True, "stderr identifies the defect"),
            replace(
                kwargs["previous"],
                analysis_and_conclusions=("repair the reported runtime error",),
            ),
        )


class SolveFailureEnvironment(ReadThenSolveEnvironment):
    def execute(self, snapshot, action, max_commands) -> ExecutionOutcome:
        if action.name == "inspect":
            return super().execute(snapshot, action, max_commands)
        self.snapshot_index += 1
        resulting = EnvironmentSnapshot(
            f"phase-{self.snapshot_index}",
            f"phase://{self.snapshot_index}",
            "broken-files",
            action.name,
        )
        result = CommandResult(
            action.commands[0],
            2,
            "",
            "runtime error with actionable stderr",
            0.0,
        )
        return ExecutionOutcome(snapshot, resulting, action, (result,))


class MCTSTests(unittest.TestCase):
    def test_verified_success_stops_immediately_by_default(self) -> None:
        config = MCTSConfig()

        self.assertTrue(config.stop_on_verified_success)
        self.assertTrue(config.require_successful_verification)
        self.assertEqual(config.post_success_iterations, 0)

    def test_verified_success_stops_before_remaining_interaction_budget(self) -> None:
        task = TaskSpec.create("repair efficiently", ("target reached",))
        result = TaskRunner(
            CounterEnvironment(),
            CoveredDirectionPolicy(),
            MCTSConfig(
                max_iterations=20,
                initial_branching_factor=1,
                expansion_width=2,
                selection_mode="working",
            ),
        ).run(task)

        self.assertTrue(result.verified_success)
        self.assertEqual(result.stop_reason, "verified_success")
        self.assertEqual(result.interaction_rounds, 2)
        self.assertEqual(result.interaction_rounds, len(result.transitions))

    def test_backpropagation_updates_every_node_and_edge_on_full_path(self) -> None:
        graph = SearchGraph()
        root = graph.add_root(
            StructuredContext(task_goal="test"),
            EnvironmentSnapshot("root", ".", "env-root", "root"),
        )
        first_action = CoveredDirectionPolicy._action("first", "first", 1)
        first, first_edge, _ = graph.add_or_merge_child(
            parent=root,
            context=StructuredContext(task_goal="test", current_solution="first"),
            snapshot=EnvironmentSnapshot("first", ".", "env-first", "first"),
            action=first_action,
            terminal=False,
            semantic_coverage_rate=0.2,
            applicable_rule_ids=(),
        )
        second_action = CoveredDirectionPolicy._action("second", "second", 1)
        second, second_edge, _ = graph.add_or_merge_child(
            parent=first,
            context=StructuredContext(task_goal="test", current_solution="second"),
            snapshot=EnvironmentSnapshot("second", ".", "env-second", "second"),
            action=second_action,
            terminal=False,
            semantic_coverage_rate=0.4,
            applicable_rule_ids=(),
        )

        CoverageGuidedMCTS._backpropagate(
            graph,
            [first_edge, second_edge],
            1.5,
        )

        for node in (root, first, second):
            self.assertEqual(node.visits, 1)
            self.assertEqual(node.total_value, 1.5)
        for edge in (first_edge, second_edge):
            self.assertEqual(edge.visits, 1)
            self.assertEqual(edge.total_value, 1.5)

    def test_working_selection_reconstructs_root_prefix_for_backpropagation(self) -> None:
        graph = SearchGraph()
        root = graph.add_root(
            StructuredContext(task_goal="test"),
            EnvironmentSnapshot("root", ".", "env-root", "root"),
        )
        action = CoveredDirectionPolicy._action("repair", "repair", 1)
        working, edge, _ = graph.add_or_merge_child(
            parent=root,
            context=StructuredContext(task_goal="test", current_solution="draft"),
            snapshot=EnvironmentSnapshot("draft", ".", "env-draft", "draft"),
            action=action,
            terminal=False,
            semantic_coverage_rate=0.5,
            applicable_rule_ids=(),
        )
        search = object.__new__(CoverageGuidedMCTS)
        search.config = MCTSConfig(selection_mode="working")
        search._solve_mode = True
        search._working_node_id = working.node_id

        start = search._working_selection_start(graph, iteration=2)
        path = search._path_from_root(graph, start.node_id)

        self.assertEqual(start, working)
        self.assertEqual(path, [edge])

    def test_working_path_keeps_actual_parent_edges_in_a_merged_dag(self) -> None:
        graph = SearchGraph()
        root = graph.add_root(
            StructuredContext(task_goal="test"),
            EnvironmentSnapshot("root", ".", "env-root", "root"),
        )
        left = SearchNode(
            "left",
            StructuredContext(task_goal="test", current_solution="left"),
            EnvironmentSnapshot("left", ".", "env-left", "left"),
        )
        right = SearchNode(
            "right",
            StructuredContext(task_goal="test", current_solution="right"),
            EnvironmentSnapshot("right", ".", "env-right", "right"),
        )
        target = SearchNode(
            "target",
            StructuredContext(task_goal="test", current_solution="merged"),
            EnvironmentSnapshot("target", ".", "env-target", "target"),
        )
        graph.nodes.update({"left": left, "right": right, "target": target})
        action = CoveredDirectionPolicy._action("move", "move", 1)
        edges = (
            SearchEdge("root-left", root.node_id, "left", action, 0.0),
            SearchEdge("left-target", "left", "target", action, 0.0),
            SearchEdge("root-right", root.node_id, "right", action, 0.0),
            SearchEdge("right-target", "right", "target", action, 0.0),
        )
        for edge in edges:
            graph.edges[edge.edge_id] = edge
            graph.nodes[edge.source_node_id].outgoing_edge_ids.append(edge.edge_id)
        search = object.__new__(CoverageGuidedMCTS)
        search._working_path_edge_ids = ("root-right", "right-target")

        path = search._working_path(graph, "target")

        self.assertEqual(
            [edge.edge_id for edge in path],
            ["root-right", "right-target"],
        )

    def test_selection_modes_support_root_working_and_hybrid_ablation(self) -> None:
        graph = SearchGraph()
        root = graph.add_root(
            StructuredContext(task_goal="test"),
            EnvironmentSnapshot("root", ".", "env-root", "root"),
        )
        action = CoveredDirectionPolicy._action("repair", "repair", 1)
        working, _, _ = graph.add_or_merge_child(
            parent=root,
            context=StructuredContext(task_goal="test", current_solution="draft"),
            snapshot=EnvironmentSnapshot("draft", ".", "env-draft", "draft"),
            action=action,
            terminal=False,
            semantic_coverage_rate=0.5,
            applicable_rule_ids=(),
        )
        search = object.__new__(CoverageGuidedMCTS)
        search._solve_mode = True
        search._working_node_id = working.node_id

        search.config = MCTSConfig(selection_mode="root")
        self.assertIsNone(search._working_selection_start(graph, iteration=1))
        search.config = MCTSConfig(selection_mode="working")
        self.assertEqual(search._working_selection_start(graph, iteration=3), working)
        search.config = MCTSConfig(
            selection_mode="hybrid",
            hybrid_root_interval=3,
        )
        self.assertEqual(search._working_selection_start(graph, iteration=2), working)
        self.assertIsNone(search._working_selection_start(graph, iteration=3))

    def test_fused_default_starts_at_root_then_keeps_working_snapshot_in_solve(self) -> None:
        graph = SearchGraph()
        root = graph.add_root(
            StructuredContext(task_goal="test"),
            EnvironmentSnapshot("root", ".", "env-root", "root"),
        )
        action = CoveredDirectionPolicy._action("repair", "repair", 1)
        working, _, _ = graph.add_or_merge_child(
            parent=root,
            context=StructuredContext(task_goal="test", current_solution="draft"),
            snapshot=EnvironmentSnapshot("draft", ".", "env-draft", "draft"),
            action=action,
            terminal=False,
            semantic_coverage_rate=0.5,
            applicable_rule_ids=(),
        )
        search = object.__new__(CoverageGuidedMCTS)
        search.config = MCTSConfig()
        search._solve_mode = False
        search._working_node_id = working.node_id

        self.assertEqual(search.config.selection_mode, "plore_ploit")
        self.assertIsNone(search._working_selection_start(graph, iteration=1))
        search._solve_mode = True
        self.assertEqual(search._working_selection_start(graph, iteration=4), working)
        self.assertEqual(search._working_selection_start(graph, iteration=8), working)

    def test_recommend_experience_guides_the_normal_mcts_ucb(self) -> None:
        plain = CoveredDirectionPolicy._action("plain", "plain", 1)
        recommended = replace(
            CoveredDirectionPolicy._action("recommended", "recommended", 1),
            applied_rule_ids=("rule-1",),
        )
        parent = SearchNode(
            "root",
            StructuredContext(task_goal="test"),
            EnvironmentSnapshot("root", ".", "env-root", "root"),
        )
        parent.visits = 10
        high_q = SearchEdge(
            "high", parent.node_id, "high-node", plain, 0.4, 2, 4.0
        )
        rule_edge = SearchEdge(
            "rule", parent.node_id, "rule-node", recommended, 0.4, 2, 0.2
        )
        search = object.__new__(CoverageGuidedMCTS)
        search.config = MCTSConfig(recommend_rule_weight=10.0)
        search._solve_mode = False

        self.assertEqual(
            max(
                (high_q, rule_edge),
                key=lambda item: search._selection_score(parent, item),
            ),
            rule_edge,
        )

    def test_solve_mode_prioritizes_pending_candidate(self) -> None:
        inspect_action = CoveredDirectionPolicy._action("inspect", "inspect", 1)
        candidate_action = CoveredDirectionPolicy._action(
            "repair",
            "repair",
            1,
            candidate=True,
        )
        node = SearchNode(
            "node",
            StructuredContext(task_goal="test"),
            EnvironmentSnapshot("node", ".", "tree", "node"),
            pending_actions=[inspect_action, candidate_action],
        )
        search = object.__new__(CoverageGuidedMCTS)
        search._solve_mode = True
        search.rule_store = TaskRuleStore(task_id="test")

        selected = search._take_pending_action(node)

        self.assertEqual(selected, candidate_action)

    def test_exploit_ablation_obeys_fixed_capacity_after_path_exhaustion(self) -> None:
        task = TaskSpec.create("inspect then repair")
        graph = SearchGraph()
        root = graph.add_root(
            StructuredContext(task_goal=task.goal),
            EnvironmentSnapshot("root", ".", "env-root", "root"),
        )
        already_tried = CoveredDirectionPolicy._action(
            "repeat_inspection",
            "inspect_requirements",
            1,
        )
        root.tried_action_ids.add(already_tried.signature())
        root.expansion_batches = 1
        root.exhausted = True
        search = object.__new__(CoverageGuidedMCTS)
        search.config = MCTSConfig(
            selection_mode="exploit",
            max_expansion_batches_per_node=1,
            expansion_width=2,
            base_children_per_node=2,
            max_children_per_node=2,
        )
        search.policy = CoveredDirectionPolicy()
        search.rule_store = TaskRuleStore(task_id=task.task_id)
        search._knowledge_board = None
        search._model_failure_count = 0
        search._solve_mode = False
        search._working_node_id = None
        search._working_path_edge_ids = ()

        selected, path = search._select(graph, task, iteration=3)
        action = search._take_pending_action(selected)

        self.assertEqual(selected, root)
        self.assertEqual(path, [])
        self.assertIsNotNone(action)
        self.assertEqual(action.name, "repair_and_test")
        self.assertEqual(root.expansion_batches, 2)
        self.assertFalse(search._can_expand_node(root))

    def test_solve_mode_removes_semantic_coverage_selection_bonus(self) -> None:
        parent = SearchNode(
            node_id="parent",
            context=StructuredContext(task_goal="test"),
            snapshot=EnvironmentSnapshot("root", ".", "fingerprint", "root"),
            visits=10,
        )
        action = CoveredDirectionPolicy._action("inspect", "inspect", 1)
        low = SearchEdge(
            "low", "parent", "low-node", action, 0.1, visits=1, total_value=1.0
        )
        high = SearchEdge(
            "high", "parent", "high-node", action, 0.9, visits=1, total_value=1.0
        )
        search = object.__new__(CoverageGuidedMCTS)
        search.config = MCTSConfig()
        search._solve_mode = True

        self.assertAlmostEqual(
            search._selection_score(parent, low),
            search._selection_score(parent, high),
        )

    def test_verified_candidate_corrects_model_false_negative_when_required(self) -> None:
        task = TaskSpec.create("accept a verified candidate")
        result = TaskRunner(
            ReadThenSolveEnvironment(),
            ReadThenSolvePolicy(),
            MCTSConfig(
                max_iterations=2,
                initial_branching_factor=1,
                expansion_width=1,
                selection_mode="working",
                require_successful_verification=True,
                post_success_iterations=0,
            ),
        ).run(task)

        self.assertTrue(result.succeeded)
        self.assertFalse(result.transitions[-1].assessment.task_success)
        self.assertTrue(result.transitions[-1].assessment.verified_success)
        self.assertEqual(result.transitions[-1].action.name, "edit")
        self.assertIn(
            "运行时根据完整成功标准覆盖与独立功能验证生成verified_success",
            result.transitions[-1].assessment.feedback,
        )

    def test_all_avoided_actions_keep_one_fallback_without_bypassing_environment(self) -> None:
        task = TaskSpec.create("complete the blocked implementation")
        store = TaskRuleStore(task_id=task.task_id)
        avoided = store.add(
            task_id=task.task_id,
            kind="avoid",
            semantic_direction_id="blocked_implementation",
            action_name="implement_fallback",
            evidence="an earlier attempt failed",
            condition="the same strategy appears applicable",
            failure_kind="strategy_failure",
            scope="semantic_strategy",
        )
        search = CoverageGuidedMCTS(
            environment=CounterEnvironment(),
            policy=AllAvoidedPolicy(avoided.rule_id),
            rule_store=store,
            mcts_config=MCTSConfig(max_iterations=1, initial_branching_factor=1),
        )

        result = search.search(
            task=task,
            initial_context=StructuredContext(task_goal=task.goal),
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(result.transitions[0].action.name, "implement_fallback")
        self.assertEqual(result.transitions[0].action.applied_rule_ids, ())

    def test_unsuccessful_search_returns_latest_modified_solution_workspace(self) -> None:
        task = TaskSpec.create("inspect and start a repair")

        result = TaskRunner(
            ReadThenSolveEnvironment(),
            ReadThenSolvePolicy(),
            MCTSConfig(
                max_iterations=2,
                initial_branching_factor=1,
                expansion_width=1,
                semantic_coverage_switch_threshold=0.6,
                #本用例检查失败任务的工作区回退，不启用“验证通过即成功”的默认策略。
                require_successful_verification=False,
            ),
        ).run(task)

        self.assertFalse(result.succeeded)
        self.assertEqual(
            [item.action.name for item in result.transitions],
            ["inspect", "edit"],
        )
        self.assertEqual(result.best_node.snapshot.fingerprint, "draft-files")

    def test_failed_modified_child_does_not_replace_last_usable_solution(self) -> None:
        task = TaskSpec.create("keep the working draft when a repair regresses")

        result = TaskRunner(
            ReadThenSolveEnvironment(),
            RegressingSolutionPolicy(),
            MCTSConfig(
                max_iterations=3,
                initial_branching_factor=1,
                expansion_width=1,
                semantic_coverage_switch_threshold=0.6,
                #保留后续回归动作，专门测试失败子节点不会覆盖工作解。
                require_successful_verification=False,
            ),
        ).run(task)

        self.assertEqual(
            [item.action.name for item in result.transitions],
            ["inspect", "edit", "corrupt"],
        )
        self.assertEqual(result.transitions[-1].assessment.direction_status, "failed")
        self.assertEqual(result.best_node.snapshot.fingerprint, "draft-files")

    def test_final_reverification_falls_back_to_earlier_verified_candidate(self) -> None:
        task = TaskSpec.create("keep an earlier candidate if final replay regresses")

        result = TaskRunner(
            LatestCandidateFailsReverifyEnvironment(),
            ReadThenSolvePolicy(),
            MCTSConfig(
                max_iterations=3,
                initial_branching_factor=1,
                expansion_width=1,
                semantic_coverage_switch_threshold=0.6,
                post_success_iterations=0,
                require_successful_verification=False,
            ),
        ).run(task)

        self.assertFalse(result.succeeded)
        self.assertEqual(result.stop_reason, "final_verification_failed")
        self.assertEqual(result.best_node.snapshot.fingerprint, "draft-files")

    def test_solve_phase_failed_cli_is_analyzed_but_cannot_advance_solution(self) -> None:
        policy = SolveFailurePolicy()
        task = TaskSpec.create("analyze a failed repair without promoting it")

        result = TaskRunner(
            SolveFailureEnvironment(),
            policy,
            MCTSConfig(
                max_iterations=2,
                initial_branching_factor=1,
                expansion_width=1,
                semantic_coverage_switch_threshold=0.6,
            ),
        ).run(task)

        failed = result.transitions[-1]
        self.assertEqual(policy.failure_updates, 1)
        self.assertEqual(failed.assessment.direction_status, "failed")
        self.assertTrue(failed.assessment.task_success)
        self.assertFalse(failed.assessment.verified_success)
        self.assertIn(
            "repair the reported runtime error",
            failed.state_after.analysis_and_conclusions,
        )
        self.assertEqual(result.best_node.snapshot.fingerprint, "root-files")

    def test_fused_scheduler_reserves_three_quarters_for_solving(self) -> None:
        task = TaskSpec.create("reserve most iterations for implementation")
        store = TaskRuleStore(task_id=task.task_id)
        search = CoverageGuidedMCTS(
            environment=CounterEnvironment(),
            policy=CoveredDirectionPolicy(),
            rule_store=store,
            mcts_config=MCTSConfig(max_iterations=24),
        )
        context = StructuredContext(task_goal=task.goal)
        graph = SearchGraph()
        root = graph.add_root(context, search.environment.initial_snapshot())
        search._knowledge_board = TaskKnowledgeBoard.create(
            root.snapshot.fingerprint,
            context,
        )

        search._maybe_activate_solve_mode(graph, 6)
        self.assertFalse(search._solve_mode)
        search._maybe_activate_solve_mode(graph, 7)
        self.assertTrue(search._solve_mode)

    def test_solve_switch_audits_missing_success_criterion_without_delay(self) -> None:
        task = TaskSpec.create("repair package", ("Generated package is verified",))
        search = CoverageGuidedMCTS(
            environment=CounterEnvironment(),
            policy=CoveredDirectionPolicy(),
            rule_store=TaskRuleStore(task_id=task.task_id),
            mcts_config=MCTSConfig(max_iterations=4),
        )
        context = StructuredContext(
            task_goal=task.goal,
            semantic_directions=(
                SemanticDirection("source", "Inspect source", "covered"),
            ),
        )
        graph = SearchGraph()
        root = graph.add_root(context, search.environment.initial_snapshot())
        search._knowledge_board = TaskKnowledgeBoard.create(
            root.snapshot.fingerprint,
            context,
        )

        search._maybe_activate_solve_mode(graph, 1, task=task)

        self.assertTrue(search._solve_mode)
        self.assertIn(
            "Generated package is verified",
            {item.label for item in graph.root().context.semantic_directions},
        )

    def test_read_only_knowledge_triggers_solve_phase_and_keeps_edit_chain(self) -> None:
        policy = ReadThenSolvePolicy()
        task = TaskSpec.create("inspect, edit, and verify")

        result = TaskRunner(
            ReadThenSolveEnvironment(),
            policy,
            MCTSConfig(
                max_iterations=4,
                initial_branching_factor=1,
                expansion_width=1,
                semantic_coverage_switch_threshold=0.6,
                #该用例显式覆盖成功后继续探索、蒸馏规则的消融路径。
                post_success_iterations=2,
                require_successful_verification=False,
            ),
        ).run(task)

        self.assertTrue(result.succeeded)
        self.assertEqual(
            [item.action.name for item in result.transitions[:3]],
            ["inspect", "edit", "fix_and_test"],
        )
        self.assertGreater(len(result.transitions), 3)
        self.assertEqual(policy.solve_flags[:2], [True, True])
        self.assertGreaterEqual(len(policy.solve_flags), 2)
        self.assertTrue(policy.saw_shared_fact)
        self.assertEqual(result.best_node.snapshot.fingerprint, "fixed-files")
        self.assertEqual({rule.kind for rule in result.rules}, {"avoid", "recommend"})
        verifier_rules = tuple(
            rule
            for rule in result.rules
            if rule.action_name == "reuse_functional_verifier"
        )
        self.assertTrue(verifier_rules)
        self.assertTrue(
            all(rule.sharing_scope == "task" for rule in verifier_rules)
        )

    def test_adaptive_budget_only_changes_operational_search_limits(self) -> None:
        simple = adapt_search_budget(
            "Fix the typo in parser.py.",
            base_iterations=24,
            base_tool_calls=80,
        )
        complex_text = "\n".join(
            [
                "Repair the cross-module behavior described below.",
                "```python",
                "Traceback (most recent call last):",
                "```",
                "- update src/a.py",
                "- update src/b.py",
                "- preserve tests/test_a.py",
                "- verify integration behavior",
            ]
            * 5
        )
        complex_budget = adapt_search_budget(
            complex_text,
            base_iterations=24,
            base_tool_calls=80,
        )

        self.assertEqual(simple.complexity, "simple")
        self.assertEqual((simple.max_iterations, simple.max_total_tool_calls), (22, 72))
        self.assertEqual(complex_budget.complexity, "complex")
        self.assertEqual(
            (complex_budget.max_iterations, complex_budget.max_total_tool_calls),
            (33, 108),
        )

    def test_success_without_real_verification_is_rejected_when_required(self) -> None:
        task = TaskSpec.create("inspect then repair", ("repair completed",))
        result = TaskRunner(
            CounterEnvironment(),
            UnverifiedSuccessPolicy(),
            MCTSConfig(
                max_iterations=2,
                initial_branching_factor=1,
                expansion_width=2,
                post_success_iterations=0,
                require_successful_verification=True,
            ),
        ).run(task)

        self.assertFalse(result.succeeded)
        rejected = result.transitions[-1]
        self.assertTrue(rejected.assessment.task_success)
        self.assertFalse(rejected.assessment.verified_success)
        self.assertEqual(rejected.reward.task_success_reward, 0.0)
        self.assertFalse(result.graph.nodes[rejected.child_node_id].terminal)
        self.assertIn("verified_success=false", rejected.assessment.feedback)

    def test_model_failure_after_successful_cli_keeps_transition_and_checkpoint(self) -> None:
        task = TaskSpec.create("keep real CLI progress")
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "search_checkpoint.json"
            result = TaskRunner(
                CounterEnvironment(),
                UnavailableTransitionPolicy(),
                MCTSConfig(max_iterations=1, initial_branching_factor=1),
                checkpoint_path=checkpoint,
            ).run(task)
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))

        self.assertEqual(len(result.transitions), 1)
        self.assertEqual(result.transitions[0].assessment.direction_status, "exploring")
        self.assertEqual(saved["transitions_completed"], 1)
        self.assertEqual(saved["interaction_rounds"], 1)
        self.assertEqual(saved["model_failures"], 1)
        self.assertEqual(saved["best_workspace"], result.best_node.snapshot.location)

    def test_initial_model_failure_returns_root_checkpoint_instead_of_raising(self) -> None:
        task = TaskSpec.create("survive an initial model outage")
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "search_checkpoint.json"
            result = TaskRunner(
                CounterEnvironment(),
                UnavailableInitialPolicy(),
                MCTSConfig(max_iterations=2, initial_branching_factor=1),
                checkpoint_path=checkpoint,
            ).run(task)
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))

        self.assertEqual(result.stop_reason, "model_unavailable")
        self.assertFalse(result.transitions)
        self.assertEqual(saved["model_failures"], 1)
        self.assertTrue(saved["best_workspace"].startswith("counter://"))

    def test_expansion_failure_skips_bad_branch_and_searches_another(self) -> None:
        task = TaskSpec.create("find the working branch")

        result = TaskRunner(
            CounterEnvironment(),
            OneBrokenBranchPolicy(),
            MCTSConfig(max_iterations=12, initial_branching_factor=2, expansion_width=1),
        ).run(task)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.stop_reason, "verified_success")
        self.assertEqual(
            [item.action.name for item in result.transitions],
            ["branch_a", "branch_b", "repair"],
        )
        self.assertEqual(
            {
                item.direction_id
                for item in result.transitions[0].state_before.semantic_directions
            },
            {"branch_a", "branch_b"},
        )

    def test_failed_cli_transition_skips_model_update(self) -> None:
        policy = FailingActionPolicy()
        task = TaskSpec.create("observe a failed command")

        result = TaskRunner(
            FailingCounterEnvironment(),
            policy,
            MCTSConfig(max_iterations=1, initial_branching_factor=1),
        ).run(task)

        self.assertEqual(policy.update_calls, 0)
        self.assertEqual(result.transitions[0].assessment.direction_status, "failed")
        self.assertIn("return code 2", result.transitions[0].assessment.feedback)
        self.assertIn("simulated command failure", result.transitions[0].assessment.feedback)

    def test_verified_fact_reaches_the_next_node_when_model_omits_it(self) -> None:
        task = TaskSpec.create("collect two facts")
        result = TaskRunner(
            CounterEnvironment(),
            ForgetfulFactsPolicy(),
            MCTSConfig(
                # Isolate compression along one modified branch, not sibling exploration.
                selection_mode="exploit",
                max_iterations=2,
                initial_branching_factor=1,
                expansion_width=1,
            ),
        ).run(task)

        final_facts = result.transitions[-1].state_after.facts_and_evidence
        self.assertTrue(
            any(
                item.claim == "Stable fact"
                and item.source == "first command"
                and item.verified == "yes"
                for item in final_facts
            ),
        )

    def test_recommend_rule_orders_pending_actions_before_edges_exist(self) -> None:
        store = TaskRuleStore(task_id="task-a")
        rule = store.add(
            task_id="task-a",
            kind="recommend",
            semantic_direction_id="recommended-direction",
            action_name="recommended",
            evidence="previously useful",
        )
        plain = CoveredDirectionPolicy._action("plain", "plain-direction", 1)
        recommended = replace(
            CoveredDirectionPolicy._action(
                "recommended",
                "recommended-direction",
                1,
            ),
            applied_rule_ids=(rule.rule_id,),
        )
        node = SearchNode(
            node_id="node-a",
            context=StructuredContext(task_goal="test"),
            snapshot=EnvironmentSnapshot("snapshot-a", ".", "fingerprint", "test"),
            pending_actions=[plain, recommended],
        )
        search = object.__new__(CoverageGuidedMCTS)
        search.rule_store = store

        selected = search._take_pending_action(node)

        self.assertEqual(selected, recommended)

    def test_covered_semantic_direction_is_not_explored_again(self) -> None:
        task = TaskSpec.create("inspect then repair", ("repair completed",))
        result = TaskRunner(
            CounterEnvironment(),
            CoveredDirectionPolicy(),
            MCTSConfig(
                selection_mode="exploit",  # Keep this two-step modified-counter chain.
                max_iterations=2, initial_branching_factor=1, expansion_width=2,
            ),
        ).run(task)

        self.assertTrue(result.succeeded)
        self.assertEqual(
            [item.action.semantic_direction_id for item in result.transitions],
            ["inspect_requirements", "repair_implementation"],
        )

    def test_demo_reaches_target_and_distills_task_rules(self) -> None:
        result = run_demo()
        self.assertTrue(result.succeeded)
        self.assertEqual(result.stop_reason, "verified_success")
        self.assertEqual(result.post_hoc_indicators.final_semantic_coverage_rate, 1.0)
        self.assertEqual(
            {rule.kind for rule in result.rules},
            {"recommend", "avoid"},
        )
        self.assertTrue(result.grpo_samples)


if __name__ == "__main__":
    unittest.main()
