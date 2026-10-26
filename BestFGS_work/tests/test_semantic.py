import json
import unittest

from cli_retrac_mcts.models import (
    CommandResult,
    CommandSpec,
    EnvironmentSnapshot,
    EvidenceItem,
    ExecutionOutcome,
    MacroAction,
    SearchGraph,
    SemanticDirection,
    StructuredContext,
)
from cli_retrac_mcts.semantic import (
    SemanticNodeMergeConfig,
    TaskKnowledgeBoard,
    invalidate_context_for_workspace_changes,
    merge_semantically_equivalent_contexts,
    merge_semantic_directions,
    merge_verified_facts,
    project_context_for_prompt,
    register_action_directions,
    semantic_coverage_rate,
    semantic_coverage_snapshot,
    set_direction_status,
)


def action(direction_id: str) -> MacroAction:
    return MacroAction.create(
        name=f"explore_{direction_id}",
        rationale="test",
        semantic_direction_id=direction_id,
        semantic_direction_label=f"Direction {direction_id}",
        commands=(CommandSpec(("tool", direction_id), "test command"),),
    )


class SemanticCoverageTests(unittest.TestCase):
    def test_fixed_core_coverage_is_not_diluted_by_newly_discovered_direction(self) -> None:
        before = StructuredContext(
            task_goal="repair",
            semantic_directions=(
                SemanticDirection("core-a", "Core A", "covered"),
                SemanticDirection("core-b", "Core B", "unexplored"),
            ),
        )
        after = StructuredContext(
            task_goal="repair",
            semantic_directions=(
                *before.semantic_directions,
                SemanticDirection("new-c", "Newly discovered C", "unexplored"),
            ),
        )

        core_ids = ("core-a", "core-b")
        self.assertEqual(
            semantic_coverage_rate(before, direction_ids=core_ids),
            semantic_coverage_rate(after, direction_ids=core_ids),
        )
        self.assertEqual(semantic_coverage_snapshot(after).total, 3)
        self.assertLess(
            semantic_coverage_rate(after),
            semantic_coverage_rate(before),
        )

    def test_file_change_invalidates_only_dependent_fact_and_reopens_its_direction(self) -> None:
        context = StructuredContext(
            task_goal="repair",
            facts_and_evidence=(
                EvidenceItem(
                    "Parser accepts valid input",
                    "src/parser.py",
                    "yes",
                    "parser",
                    workspace_dependencies=("src/parser.py",),
                    observed_at_fingerprint="before",
                ),
                EvidenceItem(
                    "CLI help is documented",
                    "docs/cli.md",
                    "yes",
                    "docs",
                    workspace_dependencies=("docs/cli.md",),
                    observed_at_fingerprint="before",
                ),
            ),
            semantic_directions=(
                SemanticDirection(
                    "parser",
                    "Parser behavior",
                    "covered",
                    ("parser test passed",),
                    ("src/parser.py",),
                    "before",
                ),
                SemanticDirection(
                    "docs",
                    "CLI documentation",
                    "covered",
                    ("documentation inspected",),
                    ("docs/cli.md",),
                    "before",
                ),
            ),
        )

        updated = invalidate_context_for_workspace_changes(
            context,
            ("src/parser.py",),
        )

        self.assertEqual(
            {item.claim for item in updated.facts_and_evidence},
            {"CLI help is documented"},
        )
        statuses = {
            item.direction_id: item.status for item in updated.semantic_directions
        }
        self.assertEqual(statuses, {"parser": "unexplored", "docs": "covered"})

    def test_task_board_does_not_inject_stale_coverage_into_changed_branch(self) -> None:
        root_context = StructuredContext(
            task_goal="repair",
            facts_and_evidence=(
                EvidenceItem(
                    "Parser mode is strict",
                    "src/parser.py",
                    "yes",
                    "parser",
                    workspace_dependencies=("src/parser.py",),
                    observed_at_fingerprint="root",
                ),
            ),
            semantic_directions=(
                SemanticDirection(
                    "parser",
                    "Parser behavior",
                    "covered",
                    ("source inspected",),
                    ("src/parser.py",),
                    "root",
                ),
            ),
        )
        board = TaskKnowledgeBoard.create("root", root_context)

        changed = board.enrich(
            StructuredContext(task_goal="repair"),
            changed_paths_from_root=("src/parser.py",),
        )

        self.assertFalse(changed.facts_and_evidence)
        self.assertEqual(changed.semantic_directions[0].status, "unexplored")
        self.assertNotIn(
            "parser",
            board.covered_direction_ids(
                changed_paths_from_root=("src/parser.py",),
            ),
        )

    def test_same_environment_semantic_equivalent_nodes_are_merged_losslessly(self) -> None:
        graph = SearchGraph()
        snapshot = EnvironmentSnapshot("root", ".", "same-files", "root")
        root = graph.add_root(StructuredContext(task_goal="repair parser"), snapshot)
        first_context = StructuredContext(
            task_goal="repair parser",
            facts_and_evidence=(
                EvidenceItem(
                    "Node.js version is v20.11.0",
                    "node --version",
                    "yes",
                    "runtime",
                ),
            ),
            unresolved_issues=("parser crash remains unresolved",),
            semantic_directions=(
                SemanticDirection("runtime", "Runtime", "exploring", ("first",)),
            ),
        )
        second_context = StructuredContext(
            task_goal="repair parser",
            facts_and_evidence=(
                EvidenceItem(
                    "Detected Node version: 20.11.0",
                    "diagnostic",
                    "yes",
                    "runtime",
                ),
            ),
            unresolved_issues=("parser crash remains unresolved",),
            semantic_directions=(
                SemanticDirection("runtime", "Runtime", "covered", ("second",)),
            ),
        )
        first, _, merged_first = graph.add_or_merge_child(
            parent=root,
            context=first_context,
            snapshot=snapshot,
            action=action("runtime"),
            terminal=False,
            semantic_coverage_rate=0.0,
            applicable_rule_ids=(),
            context_merger=merge_semantically_equivalent_contexts,
        )
        second, _, merged_second = graph.add_or_merge_child(
            parent=root,
            context=second_context,
            snapshot=snapshot,
            action=action("runtime-second"),
            terminal=False,
            semantic_coverage_rate=1.0,
            applicable_rule_ids=(),
            context_merger=merge_semantically_equivalent_contexts,
        )

        self.assertFalse(merged_first)
        self.assertTrue(merged_second)
        self.assertEqual(first.node_id, second.node_id)
        self.assertEqual(second.context.semantic_directions[0].status, "covered")
        self.assertEqual(len(second.context.facts_and_evidence), 1)
        self.assertIn("diagnostic", second.context.facts_and_evidence[0].supporting_sources)

    def test_semantic_node_merge_requires_exact_environment_fingerprint(self) -> None:
        context = StructuredContext(task_goal="test")
        graph = SearchGraph()
        root = graph.add_root(
            context,
            EnvironmentSnapshot("root", ".", "root-files", "root"),
        )
        first, _, _ = graph.add_or_merge_child(
            parent=root,
            context=context,
            snapshot=EnvironmentSnapshot("a", ".", "files-a", "a"),
            action=action("a"),
            terminal=False,
            semantic_coverage_rate=0.0,
            applicable_rule_ids=(),
            context_merger=merge_semantically_equivalent_contexts,
        )
        second, _, merged = graph.add_or_merge_child(
            parent=root,
            context=context,
            snapshot=EnvironmentSnapshot("b", ".", "files-b", "b"),
            action=action("b"),
            terminal=False,
            semantic_coverage_rate=0.0,
            applicable_rule_ids=(),
            context_merger=merge_semantically_equivalent_contexts,
        )

        self.assertFalse(merged)
        self.assertNotEqual(first.node_id, second.node_id)

    def test_semantic_node_merge_rejects_numeric_and_polarity_conflicts(self) -> None:
        direction = (SemanticDirection("runtime", "Runtime", "exploring"),)
        left = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("timeout is 30 seconds", "config", "yes", "runtime"),
                EvidenceItem("cache exists", "ls", "yes", "runtime"),
            ),
            semantic_directions=direction,
        )
        numeric_conflict = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("timeout is 60 seconds", "config", "yes", "runtime"),
                EvidenceItem("cache exists", "ls", "yes", "runtime"),
            ),
            semantic_directions=direction,
        )
        polarity_conflict = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("timeout is 30 seconds", "config", "yes", "runtime"),
                EvidenceItem("cache does not exist", "test", "yes", "runtime"),
            ),
            semantic_directions=direction,
        )

        config = SemanticNodeMergeConfig(
            verified_fact_similarity_threshold=0.0,
            unresolved_issue_similarity_threshold=0.0,
        )
        self.assertIsNone(
            merge_semantically_equivalent_contexts(left, numeric_conflict, config=config)
        )
        self.assertIsNone(
            merge_semantically_equivalent_contexts(left, polarity_conflict, config=config)
        )

    def test_task_board_shares_only_verified_facts_from_unchanged_root(self) -> None:
        inspect = action("inspect_source")
        root = EnvironmentSnapshot("root", ".", "root-fingerprint", "root")
        unchanged = EnvironmentSnapshot("read", ".", "root-fingerprint", "read")
        changed = EnvironmentSnapshot("edited", ".", "edited-fingerprint", "edited")
        result = CommandResult(inspect.commands[0], 0, "evidence", "", 0.0)
        board = TaskKnowledgeBoard.create(
            root.fingerprint,
            StructuredContext(task_goal="test"),
        )
        board.register_actions((inspect,))

        read_context = set_direction_status(
            StructuredContext(
                task_goal="test",
                facts_and_evidence=(EvidenceItem("Stable source fact", "source.c", "yes"),),
            ),
            direction_id="inspect_source",
            label="Inspect source",
            status="covered",
            evidence="source output",
        )
        absorbed = board.absorb_read_only_transition(
            read_context,
            ExecutionOutcome(root, unchanged, inspect, (result,)),
        )
        sibling = board.enrich(StructuredContext(task_goal="test"))

        self.assertTrue(absorbed)
        shared_fact = next(
            item for item in sibling.facts_and_evidence
            if item.claim == "Stable source fact"
        )
        self.assertEqual(shared_fact.verified, "yes")
        self.assertTrue(shared_fact.workspace_dependencies)
        self.assertEqual(shared_fact.observed_at_fingerprint, root.fingerprint)
        self.assertEqual(sibling.semantic_directions[0].status, "covered")

        branch_context = StructuredContext(
            task_goal="test",
            facts_and_evidence=(EvidenceItem("Branch-local edit", "edited source.c", "yes"),),
        )
        self.assertFalse(
            board.absorb_read_only_transition(
                branch_context,
                ExecutionOutcome(root, changed, inspect, (result,)),
            )
        )
        other_sibling = board.enrich(StructuredContext(task_goal="test"))
        self.assertNotIn(
            EvidenceItem("Branch-local edit", "edited source.c", "yes"),
            other_sibling.facts_and_evidence,
        )

    def test_coverage_counts_explicit_semantic_directions(self) -> None:
        context = StructuredContext(task_goal="test")
        context = register_action_directions(context, (action("a"), action("b")))
        self.assertEqual(semantic_coverage_rate(context), 0.0)

        context = set_direction_status(
            context, direction_id="a", label="A", status="covered", evidence="verified"
        )
        context = set_direction_status(
            context, direction_id="b", label="B", status="failed", evidence="failed"
        )
        self.assertEqual(semantic_coverage_rate(context), 0.5)

    def test_deferred_direction_stays_out_of_coverage_until_repeated(self) -> None:
        board = TaskKnowledgeBoard.create(
            "root",
            StructuredContext(
                task_goal="repair parser",
                semantic_directions=(SemanticDirection("core", "Inspect parser"),),
            ),
        )
        proposal = MacroAction.create(
            name="check_invalid_input",
            rationale="inspect invalid parser input",
            semantic_direction_id="invalid_input",
            semantic_direction_label="Handle invalid parser input",
            commands=(CommandSpec(("tool", "invalid"), "test invalid input"),),
        )
        context = StructuredContext(task_goal="repair parser")

        first_promotion = board.defer_actions((proposal,), (), context)
        official_after_first = board.enrich(context)
        planning_view = board.enrich_for_planning(context)

        self.assertEqual(first_promotion, ())
        self.assertEqual(board.candidate_direction_count(), 1)
        self.assertEqual(len(official_after_first.semantic_directions), 1)
        self.assertEqual(semantic_coverage_rate(official_after_first), 0.0)
        self.assertIn("invalid_input", "\n".join(planning_view.incomplete_plans))

        second_promotion = board.defer_actions((proposal,), (), context)
        official_after_second = board.enrich(context)

        self.assertEqual(len(second_promotion), 1)
        self.assertEqual(board.candidate_direction_count(), 0)
        self.assertEqual(
            {item.direction_id for item in official_after_second.semantic_directions},
            {"core", "invalid_input"},
        )

    def test_completeness_audit_maps_success_criteria_and_unresolved_issues(self) -> None:
        board = TaskKnowledgeBoard.create(
            "root",
            StructuredContext(
                task_goal="repair package",
                semantic_directions=(SemanticDirection("source", "Inspect source"),),
            ),
        )
        context = StructuredContext(
            task_goal="repair package",
            unresolved_issues=("Required wheel artifact has not been produced",),
        )

        promoted = board.audit_completeness(
            task_goal="repair package",
            success_criteria=("All regression tests pass",),
            contexts=(context,),
        )
        enriched = board.enrich(context)
        labels = {item.label for item in enriched.semantic_directions}

        self.assertEqual(len(promoted), 2)
        self.assertIn("All regression tests pass", labels)
        self.assertIn("Required wheel artifact has not been produced", labels)
        self.assertEqual(len(enriched.semantic_directions), 3)

    def test_compression_cannot_forget_covered_directions(self) -> None:
        previous = register_action_directions(
            StructuredContext(task_goal="test"), (action("a"), action("b"))
        )
        previous = set_direction_status(
            previous, direction_id="a", label="A", status="covered", evidence="proof"
        )
        compressed = StructuredContext(task_goal="test")
        merged = merge_semantic_directions(previous, compressed)
        self.assertEqual(len(merged.semantic_directions), 2)
        self.assertEqual(semantic_coverage_rate(merged), 0.5)

    def test_verified_parent_facts_are_inherited_without_downgrade(self) -> None:
        previous = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("Confirmed requirement", "README", "yes"),
                EvidenceItem("Tentative guess", "analysis", "partial"),
            ),
        )
        compressed = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("Confirmed requirement", "README", "partial"),
                EvidenceItem("New child fact", "command output", "yes"),
            ),
        )

        merged = merge_verified_facts(previous, compressed)
        facts = {
            (item.claim, item.source): item
            for item in merged.facts_and_evidence
        }

        self.assertEqual(facts[("Confirmed requirement", "README")].verified, "yes")
        self.assertIn(("New child fact", "command output"), facts)
        self.assertNotIn(("Tentative guess", "analysis"), facts)

    def test_same_fact_merges_sources_and_semantic_paraphrases(self) -> None:
        previous = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem(
                    "Node.js version is v20.11.0",
                    "node --version",
                    "yes",
                    "runtime_version",
                ),
            ),
        )
        compressed = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem(
                    "Detected Node version: 20.11.0",
                    "package diagnostic",
                    "yes",
                ),
            ),
        )

        merged = merge_verified_facts(
            previous,
            compressed,
            semantic_direction_id="runtime_version",
        )

        self.assertEqual(len(merged.facts_and_evidence), 1)
        fact = merged.facts_and_evidence[0]
        self.assertEqual(fact.semantic_direction_id, "runtime_version")
        self.assertIn("package diagnostic", fact.supporting_sources)
        self.assertIn("Detected Node version: 20.11.0", fact.aliases)

    def test_different_numeric_values_are_not_merged(self) -> None:
        previous = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("ELF entry is 0x400000", "readelf", "yes", "elf_entry"),
            ),
        )
        compressed = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("ELF entry address is 0x401000", "objdump", "yes"),
            ),
        )

        merged = merge_verified_facts(
            previous,
            compressed,
            semantic_direction_id="elf_entry",
        )

        self.assertEqual(len(merged.facts_and_evidence), 2)

    def test_opposite_polarity_facts_are_not_merged(self) -> None:
        previous = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("配置文件存在", "dir", "yes", "configuration"),
            ),
        )
        compressed = StructuredContext(
            task_goal="test",
            facts_and_evidence=(
                EvidenceItem("配置文件不存在", "test -f", "yes"),
            ),
        )

        merged = merge_verified_facts(
            previous,
            compressed,
            semantic_direction_id="configuration",
        )

        self.assertEqual(len(merged.facts_and_evidence), 2)

    def test_prompt_projection_is_bounded_and_keeps_every_direction(self) -> None:
        long_text = "diagnostic detail " * 250
        directions = tuple(
            set_direction_status(
                StructuredContext(task_goal="test"),
                direction_id=f"direction_{index}",
                label=f"Direction {index}",
                status="covered" if index % 2 else "exploring",
                evidence=long_text + str(index),
            ).semantic_directions[0]
            for index in range(12)
        )
        context = StructuredContext(
            task_goal="repair project",
            current_solution=long_text,
            facts_and_evidence=tuple(
                EvidenceItem(
                    f"fact {index} {long_text}",
                    f"command {index}",
                    "yes",
                    f"direction_{index % 12}",
                )
                for index in range(30)
            ),
            analysis_and_conclusions=tuple(long_text + str(index) for index in range(8)),
            unresolved_issues=tuple(long_text + str(index) for index in range(8)),
            incomplete_plans=tuple(long_text + str(index) for index in range(8)),
            semantic_directions=directions,
            environment_summary=long_text,
        )

        projected = project_context_for_prompt(context, max_chars=4_000)
        encoded = json.dumps(
            projected,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        self.assertLessEqual(len(encoded), 4_000)
        self.assertEqual(
            {item["direction_id"] for item in projected["semantic_directions"]},
            {f"direction_{index}" for index in range(12)},
        )
        self.assertEqual(context.current_solution, long_text)


if __name__ == "__main__":
    unittest.main()
