from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import bestfgs.experience as experience_module
from bestfgs.experience import TaskExperienceStore
from bestfgs.models import (CommandResult, CommandSpec, EnvironmentSnapshot, ExecutionOutcome,
                           MacroAction, RewardBreakdown, SemanticDirection, StructuredContext,
                           TransitionAssessment, TransitionRecord)


class TaskExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "module.py").write_text("value = 1\n", encoding="utf-8")
        (self.seed / "other.txt").write_text("unrelated\n", encoding="utf-8")
        self.store = TaskExperienceStore("task")
        self.context = StructuredContext("Fix module value", semantic_directions=(SemanticDirection("read", "Read module"),))
        self.iteration = 0

    def snapshot(self, path=None):
        path = path or self.seed
        digest = hashlib.sha256()
        for file in sorted(path.rglob("*")):
            if file.is_file():
                digest.update(file.relative_to(path).as_posix().encode())
                digest.update(file.read_bytes())
        return EnvironmentSnapshot(path.name, str(path), digest.hexdigest(), "test snapshot")

    def branch(self, name, changes):
        target = self.root / name
        shutil.copytree(self.seed, target)
        for path, value in changes.items():
            (target / path).write_text(value, encoding="utf-8")
        return self.snapshot(target)

    def action(self, *commands, verification=(), **kwargs):
        return MacroAction.create(name="read", rationale="test evidence", semantic_direction_id="read",
            semantic_direction_label="Read module", commands=tuple(commands), verification_commands=tuple(verification),
            intent="candidate" if verification or kwargs.get("submit") else "explore", **kwargs)

    def query(self):
        if shutil.which("rg") is None:
            self.skipTest("rg executable unavailable")
        return CommandSpec(("rg", "--no-config", "-n", "value", "module.py"), "read actual module")

    def transition(self, action, snapshot=None, results=None, verification_results=(), parent=None, feedback="Still investigating"):
        snapshot = snapshot or self.snapshot()
        parent = parent or snapshot
        if results is None:
            results = []
            for command in action.commands:
                output = subprocess.run(command.argv, cwd=Path(snapshot.location) / command.cwd,
                                        capture_output=True, text=True, check=False)
                results.append(CommandResult(command, output.returncode, output.stdout, output.stderr, 0.01))
        self.iteration += 1
        outcome = ExecutionOutcome(parent, snapshot, action, tuple(results), functional_validation_results=tuple(verification_results))
        return TransitionRecord("task", self.iteration, f"parent-{self.iteration}", f"child-{self.iteration}",
            action, outcome, TransitionAssessment("exploring", False, feedback), RewardBreakdown(0, 0, 0),
            self.context, self.context, 0, 0)

    def test_exploring_records_real_command_output_not_expected_effect(self):
        action = self.action(self.query(), expected_effect="THE TASK IS ALREADY SOLVED")
        transition = self.transition(action)
        records = self.store.observe(transition)
        observation = next(item for item in records if item.kind == "observation")
        self.assertIn("value = 1", observation.stdout)
        self.assertEqual(observation.return_code, 0)
        self.assertNotIn("THE TASK IS ALREADY SOLVED", json.dumps(asdict(observation)))
        self.assertTrue(any(item.kind == "hypothesis" and item.status == "unverified" for item in records))
        self.assertEqual(self.store.observe(transition), ())
        json.dumps([asdict(item) for item in self.store.all()])
        self.assertEqual(self.store.report()["by_kind"]["observation"], 1)

    def test_same_read_is_blocked_but_source_edit_permits_retry(self):
        action = self.action(self.query())
        self.store.observe(self.transition(action))
        self.assertTrue(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)
        unrelated = self.branch("unrelated-branch", {"other.txt": "different\n"})
        self.assertTrue(self.store.evaluate(action=action, snapshot=unrelated).blocked)
        changed = self.branch("repaired-branch", {"module.py": "value = 2\n"})
        decision = self.store.evaluate(action=action, snapshot=changed)
        self.assertFalse(decision.blocked)
        self.assertEqual(decision.reason, "evidence_changed_retry_allowed")
        self.assertTrue(decision.invalidated_ids)
        self.assertEqual(self.store.report()["invalidated_retry_permissions"], 1)
        self.assertIsNone(self.store.report()["false_block_rate"])

    def test_execution_environment_change_permits_retry(self):
        action = self.action(self.query())
        self.store.observe(self.transition(action))
        with patch.dict(os.environ, {"TASK_TEST_LOCALE": "changed"}):
            self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_relative_executable_search_path_is_not_a_known_condition(self):
        action = self.action(self.query())
        with patch.dict(os.environ, {"PATH": "." + os.pathsep + os.environ["PATH"]}):
            result = CommandResult(action.commands[0], 0, "value = 1", "", 0)
            record = self.store.observe(self.transition(action, results=(result,)))[0]
            self.assertEqual(record.dependency_status, "unknown")
            self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_outside_file_dependency_is_never_a_hard_block(self):
        (self.root / "outside.txt").write_text("value = 1\n", encoding="utf-8")
        command = replace(self.query(), argv=("rg", "--no-config", "value", "../outside.txt"))
        action = self.action(command)
        self.store.observe(self.transition(action))
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_unknown_test_network_shell_and_timeout_never_hard_block(self):
        cases = [
            CommandSpec((sys.executable, "-c", "print('read')"), "read by unknown code"),
            CommandSpec(("curl", "https://example.org"), "network"),
            CommandSpec(("sh", "-c", "cat module.py"), "shell"),
            CommandSpec(("rg", "--files", "."), "directory enumeration"),
        ]
        for command in cases:
            with self.subTest(command=command.argv):
                action = self.action(command)
                result = CommandResult(command, 0, "observed", "", 0)
                self.store.observe(self.transition(action, results=(result,)))
                self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)
        command = self.query()
        action = self.action(command)
        result = CommandResult(command, 124, "partial", "timeout", 1, timed_out=True)
        self.store.observe(self.transition(action, results=(result,)))
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_mixed_or_partial_macro_does_not_certify_intermediate_read(self):
        command = self.query()
        edit = CommandSpec((sys.executable, "-c", "pass"), "possible state mutation")
        action = self.action(command, edit)
        result = CommandResult(command, 0, "value = 1", "", 0)
        self.store.observe(self.transition(action, results=(result,)))
        self.assertFalse(self.store.evaluate(action=self.action(command), snapshot=self.snapshot()).blocked)

    def test_whole_macro_is_not_blocked_when_one_query_is_new(self):
        command = self.query()
        self.store.observe(self.transition(self.action(command)))
        new = replace(command, argv=("rg", "--no-config", "value", "other.txt"))
        self.assertFalse(self.store.evaluate(action=self.action(command, new), snapshot=self.snapshot()).blocked)

    def test_submit_and_verification_are_never_replaced_by_read_memory(self):
        command = self.query()
        self.store.observe(self.transition(self.action(command)))
        action = self.action(command, verification=(CommandSpec((sys.executable, "-c", "assert True"), "fresh check"),), submit=True)
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_retrieval_preserves_provenance_and_changed_conditions(self):
        self.store.observe(self.transition(self.action(self.query())))
        changed = self.branch("changed", {"module.py": "value = 4\n"})
        rules = self.store.retrieve(context=self.context, snapshot=changed, limit=5)
        observation = next(rule for rule in rules if rule.experience_kind == "observation")
        self.assertEqual(observation.condition_status, "changed")
        self.assertFalse(observation.hard_block_eligible)
        self.assertEqual(observation.dependency_paths, ("module.py",))
        self.assertEqual(observation.evidence_ids, (observation.rule_id,))
        self.assertIn("output_sha256", observation.evidence[0])
        self.assertIn("value = 1", observation.evidence[0])

    def test_bounded_output_retains_digest_of_untruncated_result(self):
        command = self.query()
        action = self.action(command)
        first = CommandResult(command, 0, "x" * 5000 + "A", "", 0)
        second = replace(first, stdout="x" * 5000 + "B")
        one = self.store.observe(self.transition(action, results=(first,)))[0]
        two = self.store.observe(self.transition(action, results=(second,)))[0]
        self.assertEqual(one.stdout, two.stdout)
        self.assertNotEqual(one.output_sha256, two.output_sha256)
        self.assertLessEqual(len(one.stdout), 1200)
        self.assertTrue(one.output_truncated)
        self.assertFalse(one.hard_block_eligible)
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_truncated_stderr_also_allows_a_complete_reread(self):
        command = self.query()
        action = self.action(command)
        result = CommandResult(command, 0, "value = 1", "warning " * 200, 0)
        record = self.store.observe(self.transition(action, results=(result,)))[0]
        self.assertTrue(record.output_truncated)
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)
        rule = self.store.retrieve(context=self.context, snapshot=self.snapshot(), limit=1)[0]
        self.assertIn("truncated", rule.guidance)

    def test_upstream_truncation_flag_prevents_hard_block_even_for_short_output(self):
        command = self.query()
        action = self.action(command)
        result = CommandResult(command, 0, "short retained tail", "", 0, output_truncated=True)
        record = self.store.observe(self.transition(action, results=(result,)))[0]
        self.assertTrue(record.output_truncated)
        self.assertFalse(record.hard_block_eligible)
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_block_feedback_carries_complete_evidence_even_when_not_retrieved(self):
        command = self.query()
        action = self.action(command)
        result = CommandResult(command, 0, "x" * 1100 + "IMPORTANT OUTPUT TAIL", "y" * 1000 + "WARNING TAIL", 0)
        record = self.store.observe(self.transition(action, results=(result,)))[0]
        self.assertEqual(self.store.retrieve(context=self.context, snapshot=self.snapshot(), limit=0), ())
        decision = self.store.evaluate(action=action, snapshot=self.snapshot())
        self.assertTrue(decision.blocked)
        self.assertIn(record.evidence_id, decision.feedback[0])
        self.assertIn(result.stdout, decision.feedback[0])
        self.assertIn(result.stderr, decision.feedback[0])
        first_count = self.store.report()["valid_duplicate_candidates"]
        self.store.evaluate(action=action, snapshot=self.snapshot())
        self.assertEqual(self.store.report()["valid_duplicate_candidates"], first_count)

    def test_conflicting_same_condition_outputs_withdraw_hard_block(self):
        command = self.query()
        action = self.action(command)
        first = CommandResult(command, 0, "first observation", "", 0)
        second = replace(first, stdout="different observation")
        self.store.observe(self.transition(action, results=(first,)))
        self.assertTrue(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)
        transition = self.transition(action, results=(second,))
        self.store.observe(transition)
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)
        rules = self.store.retrieve(context=self.context, snapshot=self.snapshot(), limit=20)
        observations = [item for item in rules if item.experience_kind == "observation"]
        self.assertTrue(observations)
        self.assertTrue(all(not item.hard_block_eligible for item in observations))
        self.assertTrue(all("conflicting" in item.guidance for item in observations))
        self.assertEqual(self.store.report()["conflicting_same_condition_observations"], 1)
        self.store.observe(transition)
        self.assertEqual(self.store.report()["conflicting_same_condition_observations"], 1)

    def test_file_hash_is_fresh_even_if_snapshot_metadata_is_reused(self):
        command = self.query()
        action = self.action(command)
        snapshot = self.snapshot()
        self.store.observe(self.transition(action, snapshot=snapshot))
        self.assertTrue(self.store.evaluate(action=action, snapshot=snapshot).blocked)
        (self.seed / "module.py").write_text("value = 9\n", encoding="utf-8")
        self.assertFalse(self.store.evaluate(action=action, snapshot=snapshot).blocked)

    def test_executable_digest_cache_is_limited_to_one_inspection(self):
        action = self.action(self.query())
        self.store.observe(self.transition(action))
        self.store.observe(self.transition(action))
        binary = Path(shutil.which("rg")).resolve()
        with patch.object(experience_module, "_file_digest", wraps=experience_module._file_digest) as digest:
            self.store.retrieve(context=self.context, snapshot=self.snapshot(), limit=20)
            binary_reads = [call for call in digest.call_args_list if call.args[0] == binary]
            self.assertEqual(len(binary_reads), 1)
            self.store.retrieve(context=self.context, snapshot=self.snapshot(), limit=20)
            binary_reads = [call for call in digest.call_args_list if call.args[0] == binary]
            self.assertEqual(len(binary_reads), 2)

    def test_failure_recurrence_is_observed_not_a_causal_metric(self):
        command = CommandSpec((sys.executable, "-c", "raise AssertionError('known failing case')"), "failing case")
        action = self.action(command)
        self.store.observe(self.transition(action))
        self.store.observe(self.transition(action))
        report = self.store.report()
        self.assertEqual(report["same_condition_failure_reobserved"], 1)
        self.assertFalse(report["failure_recurrence_is_causal"])
        self.assertFalse(self.store.evaluate(action=action, snapshot=self.snapshot()).blocked)

    def test_failed_public_script_replays_after_source_edit_but_not_script_edit(self):
        (self.seed / "check.py").write_text("from module import value\nassert value == 2\n", encoding="utf-8")
        command = CommandSpec((sys.executable, "check.py"), "public reproducer")
        action = self.action(verification=(command,))
        output = subprocess.run(command.argv, cwd=self.seed, capture_output=True, text=True)
        result = CommandResult(command, output.returncode, output.stdout, output.stderr, 0.01)
        self.assertNotEqual(result.return_code, 0)
        self.store.observe(self.transition(action, results=(), verification_results=(result,)))
        repaired = self.branch("fixed", {"module.py": "value = 2\n"})
        obligations = self.store.verification_obligations(action=action, snapshot=repaired)
        self.assertEqual(obligations, (command,))
        self.assertFalse(self.store.evaluate(action=action, snapshot=repaired).blocked)
        edited_test = self.branch("test-changed", {"check.py": "assert True\n"})
        self.assertEqual(self.store.verification_obligations(action=action, snapshot=edited_test), ())

    def test_passed_or_environment_failed_checks_never_create_failure_obligation(self):
        (self.seed / "check.py").write_text("assert True\n", encoding="utf-8")
        command = CommandSpec((sys.executable, "check.py"), "public check")
        action = self.action(verification=(command,))
        for result in (CommandResult(command, 0, "passed", "", 0),
                       CommandResult(command, 1, "", "ModuleNotFoundError: missing package", 0),
                       CommandResult(command, 1, "", "Verification modified candidate files: module.py", 0),
                       CommandResult(command, 124, "", "timed out", 1, timed_out=True)):
            self.store.observe(self.transition(action, results=(), verification_results=(result,)))
        self.assertEqual(self.store.verification_obligations(action=action, snapshot=self.snapshot()), ())
        self.assertEqual(self.store.report()["by_kind"]["reusable_verifier"], 4)

    def test_ordinary_failure_cannot_become_public_verifier(self):
        (self.seed / "check.py").write_text("assert False\n", encoding="utf-8")
        command = CommandSpec((sys.executable, "check.py"), "ordinary diagnosis")
        action = self.action(command)
        self.store.observe(self.transition(action))
        self.assertEqual(self.store.verification_obligations(action=action, snapshot=self.snapshot()), ())

    def test_task_scope_is_enforced(self):
        transition = self.transition(self.action(self.query()))
        with self.assertRaises(ValueError):
            self.store.observe(replace(transition, task_id="other-task"))


if __name__ == "__main__":
    unittest.main()
