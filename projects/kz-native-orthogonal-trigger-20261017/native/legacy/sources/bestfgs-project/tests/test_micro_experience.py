from dataclasses import asdict, replace
import hashlib
import io
import json
from pathlib import Path
import os
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import bestfgs.micro_experience as micro_module
from bestfgs.micro_experience import MicroExperienceIndex
from bestfgs.models import (CommandSpec, ConditionalExperience, EnvironmentSnapshot, ExperiencePremise,
                           MacroAction, SemanticDirection, StructuredContext)


class MicroExperienceIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "branch"
        self.workspace.mkdir()
        (self.workspace / "alpha.py").write_text("mode = 'strict'\n", encoding="utf-8")
        (self.workspace / "beta.py").write_text("boundary = 1\n", encoding="utf-8")
        self.snapshot = EnvironmentSnapshot("branch", str(self.workspace), "tree-one", "test")
        self.index = MicroExperienceIndex("task")
        self.serial = 0
        self.context = StructuredContext("Fix alpha.py and beta.py", semantic_directions=(SemanticDirection("inspect", "Inspect"),))

    def action(self, *, operation="", targets=(), premises=(), commands=()):
        return MacroAction.create(name="inspect", rationale="offline", semantic_direction_id="inspect",
            semantic_direction_label="Inspect", commands=tuple(commands),
            experience_operation=operation, experience_targets=tuple(targets), experience_premises=tuple(premises))

    def record(self, *, target="alpha.py", output="found strict mode", known=True, status="succeeded",
               truncated=False, snapshot=None, command=None, kind="observation", claim="Observed source lookup"):
        self.serial += 1
        snapshot = snapshot or self.snapshot
        command = command or CommandSpec(("rg", "--no-config", "mode", target), "lookup")
        signature = next(iter(self.index._command_signatures(self.action(commands=(command,)), snapshot)))
        path = Path(snapshot.location) / target
        dependencies = (SimpleNamespace(path=target, sha256=hashlib.sha256(path.read_bytes()).hexdigest()),) if known and path.is_file() else ()
        return SimpleNamespace(evidence_id=f"evidence-{self.serial}", task_id="task", kind=kind,
            source_channel="command", source_index=0, command_signature=signature,
            canonical_argv=command.argv, canonical_cwd=".", file_dependencies=dependencies,
            environment_token="known-executor", dependency_status="known" if known else "unknown",
            observed_snapshot_id=snapshot.snapshot_id, fallback_snapshot=snapshot.fingerprint,
            output_sha256=hashlib.sha256(output.encode()).hexdigest(), status=status,
            output_truncated=truncated, claim=claim, semantic_direction_id="inspect",
            semantic_direction_label="Inspect", counterexample_guidance="Rerun after a relevant change",
            stdout=output, stderr="", command=command)

    def add(self, record):
        return self.index.add(record, SimpleNamespace(task_id="task", action=self.action()))

    def hint(self, *, operation="update_mode", targets=("alpha.py",), premises=(), lesson="Under this premise inspect normalization", **kwargs):
        return ConditionalExperience(operation, tuple(targets), tuple(premises), "command", 0, lesson,
                                     kwargs.get("next_check", "Inspect a boundary case"))

    def lesson(self, hint=None, record=None):
        record = record or self.record()
        self.add(record)
        return self.index.add_lesson(hint or self.hint(), record, self.snapshot)

    @staticmethod
    def valid(record, snapshot):
        if record.dependency_status != "known":
            return "unknown" if record.observed_snapshot_id == snapshot.snapshot_id else "changed"
        for dependency in record.file_dependencies:
            path = Path(snapshot.location) / dependency.path
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != dependency.sha256:
                return "changed"
        return "valid"

    def matches(self, action, snapshot=None, limit=20):
        return self.index.match_action(action=action, snapshot=snapshot or self.snapshot,
            limit=limit, validity_callback=self.valid)

    def test_same_command_conditions_and_output_aggregate_all_sources_idempotently(self):
        records = [self.record() for _ in range(30)]
        for record in records:
            self.add(record)
        self.add(records[0])
        self.assertEqual(len(self.index.all()), 1)
        entry = self.index.all()[0]
        self.assertEqual(set(entry.source_ids), {item.evidence_id for item in records})
        self.assertEqual(entry.representative_id, records[-1].evidence_id)
        self.assertFalse(self.index.report()["repetition_is_independent_confidence"])
        json.dumps([asdict(entry) for entry in self.index.all()])

    def test_different_results_and_unknown_snapshots_are_not_merged(self):
        self.add(self.record(output="one"))
        self.add(self.record(output="two"))
        self.add(self.record(known=False, snapshot=replace(self.snapshot, snapshot_id="unknown-one")))
        self.add(self.record(known=False, snapshot=replace(self.snapshot, snapshot_id="unknown-two")))
        self.assertEqual(len(self.index.all()), 4)

    def test_known_dependencies_can_aggregate_and_match_across_branches(self):
        other = self.root / "other-branch"
        other.mkdir()
        (other / "alpha.py").write_bytes((self.workspace / "alpha.py").read_bytes())
        snapshot = EnvironmentSnapshot("other", str(other), "tree-two", "another branch")
        first = self.record()
        second = self.record(snapshot=snapshot)
        self.add(first)
        self.add(second)
        self.assertEqual(len(self.index.all()), 1)
        match = self.matches(self.action(commands=(first.command,)), snapshot)[0]
        self.assertEqual(match.source_validity, "valid")
        self.assertEqual(len(match.entry.source_ids), 2)
        self.assertFalse(match.hard_block_eligible)

    def test_repetitions_do_not_flood_topk_and_distinct_files_get_slots(self):
        for _ in range(40):
            self.add(self.record())
        for index in range(4):
            self.add(self.record(output=f"different observed result {index}"))
        self.add(self.record(target="beta.py", output="boundary finding"))
        matches = self.index.retrieve(context=self.context, snapshot=self.snapshot, limit=2, validity_callback=self.valid)
        self.assertEqual(len(matches), 2)
        self.assertEqual({match.entry.target_paths for match in matches}, {("alpha.py",), ("beta.py",)})

    def test_current_issue_outranks_broad_goal_and_repeated_observations(self):
        for _ in range(30):
            self.add(self.record(claim="alpha alpha strict normalization"))
        self.add(self.record(target="beta.py", output="boundary condition", claim="beta boundary"))
        context = replace(self.context, task_goal="alpha strict normalization", unresolved_issues=("Investigate beta.py boundary",))
        match = self.index.retrieve(context=context, snapshot=self.snapshot, limit=1, validity_callback=self.valid)[0]
        self.assertEqual(match.entry.target_paths, ("beta.py",))
        self.assertIn("current_issue_or_plan_file_overlap", match.match_reasons)

    def test_output_token_index_explains_why_observation_was_retrieved(self):
        self.add(self.record(output="specific_decoder_defect", claim="An observation"))
        context = StructuredContext("specific_decoder_defect")
        matches = self.index.retrieve(context=context, snapshot=self.snapshot, limit=2, validity_callback=self.valid)
        self.assertTrue(matches)
        self.assertTrue(any("token_overlap" in reason for reason in matches[0].match_reasons))

    def test_python_word_or_general_operation_alone_does_not_match_candidate(self):
        record = self.record(known=False, command=CommandSpec(("python", "-c", "print(1)"), "diagnosis"))
        self.lesson(self.hint(operation="python", targets=()), record)
        action = self.action(operation="python", commands=(CommandSpec(("python", "-c", "print(2)"), "different"),))
        self.assertEqual(self.matches(action), ())

    def test_opposite_explicit_premise_is_reported_as_declared_changed_not_blocked(self):
        premise = ExperiencePremise("mode", "equals", "strict")
        self.lesson(self.hint(premises=(premise,)))
        action = self.action(operation="update_mode", targets=("alpha.py",),
                             premises=(ExperiencePremise("mode", "equals", "loose"),))
        matches = [match for match in self.matches(action) if match.entry.kind == "conditional_hypothesis"]
        self.assertEqual(matches[0].condition_status, "declared_changed")
        self.assertEqual(matches[0].premise_states[0].status, "declared_changed")
        self.assertFalse(matches[0].hard_block_eligible)
        self.assertEqual(matches[0].entry.trust, "unverified")
        self.assertIn("model_conditional_hypothesis_not_causal_proof", matches[0].match_reasons)

    def test_semantic_values_are_literal_not_casefolded_or_underscore_normalized(self):
        for expected, declared in (("None", "none"), ("UserID", "userid"), ("a_b", "a b")):
            with self.subTest(expected=expected):
                entry = self.lesson(self.hint(premises=(ExperiencePremise("mode", "equals", expected),)))
                action = self.action(operation="update_mode", targets=("alpha.py",),
                                     premises=(ExperiencePremise("mode", "equals", declared),))
                match = next(item for item in self.matches(action) if item.entry.micro_id == entry.micro_id)
                self.assertEqual(match.condition_status, "declared_changed")

    def test_semantic_subjects_are_literal_and_context_text_does_not_verify_them(self):
        entry = self.lesson(self.hint(premises=(ExperiencePremise("UserID", "equals", "A"),)))
        action = self.action(operation="update_mode", targets=("alpha.py",),
                             premises=(ExperiencePremise("userid", "equals", "A"),))
        match = next(item for item in self.matches(action) if item.entry.micro_id == entry.micro_id)
        self.assertEqual(match.premise_states[0].status, "unknown")
        context = replace(self.context, analysis_and_conclusions=("UserID equals A",))
        retrieved = self.index.retrieve(context=context, snapshot=self.snapshot, limit=20, validity_callback=self.valid)
        match = next(item for item in retrieved if item.entry.micro_id == entry.micro_id)
        self.assertEqual(match.condition_status, "unknown")

    def test_not_equals_requires_decisive_declaration(self):
        entry = self.lesson(self.hint(premises=(ExperiencePremise("mode", "not_equals", "A"),)))
        for predicate, value, expected in (("equals", "B", "declared_match"),
                                            ("equals", "A", "declared_changed"),
                                            ("not_equals", "B", "unknown")):
            action = self.action(operation="update_mode", targets=("alpha.py",), premises=(ExperiencePremise("mode", predicate, value),))
            match = next(item for item in self.matches(action) if item.entry.micro_id == entry.micro_id)
            self.assertEqual(match.condition_status, expected)

    def test_multiple_conditions_are_and_and_rechecked_after_file_edit(self):
        premises = (ExperiencePremise("alpha.py", "file_contains", "strict"), ExperiencePremise("mode", "equals", "strict"))
        entry = self.lesson(self.hint(premises=premises))
        action = self.action(operation="update_mode", targets=("alpha.py",), premises=(premises[1],))
        match = next(item for item in self.matches(action) if item.entry.micro_id == entry.micro_id)
        self.assertEqual(match.condition_status, "declared_match")
        (self.workspace / "alpha.py").write_text("mode = 'loose'\n", encoding="utf-8")
        match = next(item for item in self.matches(action) if item.entry.micro_id == entry.micro_id)
        self.assertEqual(match.condition_status, "changed")
        self.assertEqual([item.status for item in match.premise_states], ["changed", "declared_match"])
        self.assertIn("conditions_changed_or_unconfirmed_retry_allowed", match.match_reasons)

    def test_unsafe_file_premises_are_unknown(self):
        outside = self.root / "outside.txt"
        outside.write_text("private literal", encoding="utf-8")
        # Bypass wire validation to exercise the index's independent safe reader.
        for subject in ("../outside.txt", str(outside), "alpha.py:stream"):
            premise = SimpleNamespace(subject=subject, predicate="file_contains", value="private")
            hint = SimpleNamespace(operation="update_mode", target_paths=("alpha.py",), premises=(premise,),
                source_channel="command", source_index=0, lesson="untrusted path", next_check="")
            entry = self.lesson(hint)
            match = next(item for item in self.matches(self.action(operation="update_mode", targets=("alpha.py",))) if item.entry.micro_id == entry.micro_id)
            self.assertEqual(match.premise_states[0].status, "unknown")

    def test_symlink_file_premise_does_not_read_its_target(self):
        outside = self.root / "outside.txt"
        outside.write_text("private literal", encoding="utf-8")
        link = self.workspace / "link.txt"
        try:
            os.symlink(outside, link)
        except OSError as error:
            self.skipTest(f"symlink creation unavailable: {error}")
        entry = self.lesson(self.hint(premises=(ExperiencePremise("link.txt", "file_contains", "private"),)))
        match = next(item for item in self.matches(self.action(operation="update_mode", targets=("alpha.py",))) if item.entry.micro_id == entry.micro_id)
        self.assertEqual(match.premise_states[0].status, "unknown")

    def test_windows_reparse_flag_and_redirected_ancestor_are_rejected(self):
        fake_path = SimpleNamespace(lstat=lambda: SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400))
        self.assertTrue(micro_module._is_redirect(fake_path))
        redirected = self.workspace / "redirected"
        redirected.mkdir()
        premise = ExperiencePremise("redirected/secret.txt", "file_absent")
        entry = self.lesson(self.hint(premises=(premise,)))
        original = micro_module._is_redirect
        with patch.object(micro_module, "_is_redirect", side_effect=lambda path: path == redirected or original(path)):
            match = next(item for item in self.matches(self.action(operation="update_mode", targets=("alpha.py",))) if item.entry.micro_id == entry.micro_id)
        self.assertEqual(match.premise_states[0].status, "unknown")
        self.assertEqual(match.premise_states[0].reason, "symlink_or_reparse_dependency")

    def test_timeout_blocked_and_truncated_sources_never_become_trusted(self):
        for status, truncated in (("timeout", False), ("blocked", False), ("succeeded", True)):
            entry = self.lesson(self.hint(premises=(ExperiencePremise("alpha.py", "file_exists"),)),
                                self.record(status=status, truncated=truncated))
            self.assertFalse(entry.source_evidence_usable)
            action = self.action(operation="update_mode", targets=("alpha.py",))
            match = next(item for item in self.matches(action) if item.entry.micro_id == entry.micro_id)
            self.assertEqual(match.source_validity, "unknown")
            self.assertEqual(match.entry.trust, "unverified")

    def test_invalid_source_channel_index_and_task_are_rejected(self):
        record = self.record()
        self.assertIsNone(self.index.add_lesson(self.hint(), record, self.snapshot))
        self.add(record)
        self.assertIsNone(self.index.add_lesson(replace(self.hint(), source_index=1), record, self.snapshot))
        self.assertIsNone(self.index.add_lesson(replace(self.hint(), source_channel="functional_validation"), record, self.snapshot))
        self.assertIsNone(self.index.add_lesson(self.hint(), record, replace(self.snapshot, snapshot_id="unrelated")))
        alien = self.record()
        alien.task_id = "another-task"
        with self.assertRaises(ValueError):
            self.add(alien)
        with self.assertRaises(ValueError):
            self.index.add_lesson(self.hint(), alien, self.snapshot)

    def test_next_check_is_text_only_and_hypotheses_never_hard_block(self):
        entry = self.lesson(self.hint(next_check="python danger.py --delete-everything",
                                     premises=(ExperiencePremise("alpha.py", "file_exists"),)))
        matches = self.matches(self.action(operation="update_mode", targets=("alpha.py",)))
        match = next(item for item in matches if item.entry.micro_id == entry.micro_id)
        self.assertEqual(match.entry.next_check, "python danger.py --delete-everything")
        self.assertFalse(match.hard_block_eligible)
        self.assertFalse(self.index.report()["learned_utility"])
        json.dumps(asdict(match))

    def test_file_content_is_shared_within_call_but_next_call_rereads(self):
        for predicate, value in (("file_contains", "strict"), ("file_lacks", "legacy"), ("file_contains", "mode")):
            self.lesson(self.hint(premises=(ExperiencePremise("alpha.py", predicate, value),)))
        callback = lambda record, snapshot: "valid"
        original_open = Path.open
        with patch.object(Path, "open", autospec=True, side_effect=original_open) as reads:
            def binary_reads():
                return sum(call.kwargs.get("mode", call.args[1] if len(call.args) > 1 else "r") == "rb"
                           for call in reads.call_args_list)
            self.index.retrieve(context=self.context, snapshot=self.snapshot, limit=20, validity_callback=callback)
            self.assertEqual(binary_reads(), 1)
            report = self.index.report()
            self.assertEqual(report["premise_checks"], 3)
            self.assertEqual(report["file_read_operations"], 1)
            self.assertEqual(report["file_read_bytes"], (self.workspace / "alpha.py").stat().st_size)
            self.index.match_action(action=self.action(operation="update_mode", targets=("alpha.py",)),
                                    snapshot=self.snapshot, limit=20, validity_callback=callback)
            self.assertEqual(binary_reads(), 2)
            (self.workspace / "alpha.py").write_text("mode = 'loose'\n", encoding="utf-8")
            matches = self.index.retrieve(context=self.context, snapshot=self.snapshot, limit=20, validity_callback=callback)
            self.assertEqual(binary_reads(), 3)
            strict = next(item for item in matches if item.premise_states and item.premise_states[0].value == "strict")
            self.assertEqual(strict.premise_states[0].status, "changed")
        report = self.index.report()
        self.assertEqual(report["premise_checks"], 9)
        self.assertEqual(report["file_read_operations"], 3)
        self.assertGreaterEqual(report["premise_check_seconds"], 0)
        self.assertIn("excludes source-validity callbacks", report["condition_check_cost_scope"])

    def test_file_content_cache_never_crosses_branch(self):
        entry = self.lesson(self.hint(premises=(ExperiencePremise("alpha.py", "file_contains", "strict"),)))
        other = self.root / "different-branch"
        other.mkdir()
        (other / "alpha.py").write_text("mode = 'loose'\n", encoding="utf-8")
        snapshot = replace(self.snapshot, location=str(other), snapshot_id="different")
        first = self.index.retrieve(context=self.context, snapshot=self.snapshot, limit=20, validity_callback=lambda *_: "valid")
        second = self.index.retrieve(context=self.context, snapshot=snapshot, limit=20, validity_callback=lambda *_: "valid")
        self.assertEqual(next(item for item in first if item.entry.micro_id == entry.micro_id).premise_states[0].status, "valid")
        self.assertEqual(next(item for item in second if item.entry.micro_id == entry.micro_id).premise_states[0].status, "changed")
        self.assertEqual(self.index.report()["file_read_operations"], 2)

    def test_action_topk_reserves_one_related_conditional_category_slot(self):
        (self.workspace / "gamma.py").write_text("mode = 'other'\n", encoding="utf-8")
        records = [self.record(target=path) for path in ("alpha.py", "beta.py", "gamma.py")]
        for record in records:
            self.add(record)
        premise = ExperiencePremise("mode", "equals", "strict")
        related = self.index.add_lesson(self.hint(premises=(premise,)), records[0], self.snapshot)
        unrelated = self.index.add_lesson(self.hint(operation="delete_cache", premises=(premise,)), records[0], self.snapshot)
        action = self.action(operation="update_mode", targets=("alpha.py", "beta.py", "gamma.py"),
                             premises=(premise,), commands=tuple(record.command for record in records))
        matches = self.matches(action, limit=3)
        self.assertEqual(len(matches), 3)
        conditional = next(item for item in matches if item.entry.micro_id == related.micro_id)
        self.assertIn("action_stage_conditional_category_slot", conditional.match_reasons)
        self.assertNotIn(unrelated.micro_id, {item.entry.micro_id for item in matches})
        self.assertTrue(all(not item.hard_block_eligible for item in matches))

    def test_file_content_read_remains_bounded_when_file_grows_after_stat(self):
        entry = self.lesson(self.hint(premises=(ExperiencePremise("alpha.py", "file_contains", "strict"),)))

        class GrowingFile(io.BytesIO):
            requested = None

            def read(self, size=-1):
                self.requested = size
                return super().read(size)

        stream = GrowingFile(b"x" * (micro_module._MAX_FILE_BYTES + 50))
        with patch.object(Path, "open", return_value=stream):
            matches = self.index.retrieve(context=self.context, snapshot=self.snapshot, limit=20,
                                          validity_callback=lambda *_: "valid")
        match = next(item for item in matches if item.entry.micro_id == entry.micro_id)
        self.assertEqual(stream.requested, micro_module._MAX_FILE_BYTES + 1)
        self.assertEqual(match.premise_states[0].status, "unknown")
        self.assertEqual(match.premise_states[0].reason, "file_grew_beyond_read_limit")
        self.assertEqual(self.index.report()["file_read_bytes"], micro_module._MAX_FILE_BYTES + 1)

    def test_disjoint_explicit_targets_cannot_match_via_generic_premise_subject(self):
        premise = ExperiencePremise("input", "equals", "text")
        self.lesson(self.hint(premises=(premise,)))
        action = self.action(operation="update_mode", targets=("beta.py",), premises=(premise,))
        self.assertEqual(self.matches(action), ())
        # Missing file scope may still use an explicit operation and subject.
        action = self.action(operation="update_mode", premises=(premise,))
        self.assertTrue(any(item.entry.kind == "conditional_hypothesis" for item in self.matches(action)))


if __name__ == "__main__":
    unittest.main()
