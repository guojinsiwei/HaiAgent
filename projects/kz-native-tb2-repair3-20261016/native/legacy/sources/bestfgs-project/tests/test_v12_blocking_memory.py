"""Offline blocker-ledger tests; generated diagnostics execute real stdlib code."""
from dataclasses import replace
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

from bestfgs.blocking_memory import BlockingMemory, PROBE_MARKER
from bestfgs.models import CommandResult, CommandSpec, EnvironmentSnapshot, ExecutionOutcome, MacroAction


class BlockingMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "source.py").write_text("value=1\n", encoding="utf-8")
        self.memory = BlockingMemory(self.seed)
        self.missing = CommandSpec((sys.executable, "missing.py"), "run the script")

    def snapshot(self, path=None):
        path = path or self.seed
        digest = hashlib.sha256()
        for entry in sorted(path.rglob("*")):
            digest.update(entry.relative_to(path).as_posix().encode())
            if entry.is_file():
                digest.update(entry.read_bytes())
        return EnvironmentSnapshot(path.name, str(path), digest.hexdigest(), "test")

    def failure(self, command=None, stderr=None, **kwargs):
        return CommandResult(command or self.missing, 2, "", stderr or "python: can't open file 'missing.py': [Errno 2] No such file or directory", .01, **kwargs)

    def observe(self, results=None, *, before=None, after=None, metadata=None):
        results = tuple(results or [self.failure()])
        before = before or self.snapshot()
        after = after or before
        action = MacroAction.create(name="test", rationale="test", semantic_direction_id="t",
                                    semantic_direction_label="t", commands=tuple(r.command for r in results),
                                    **(metadata or {}))
        self.memory.observe(action, ExecutionOutcome(before, after, action, results), before)

    def run_probe(self, decision, *, turn=1, snapshot=None, mutate=None):
        snapshot = snapshot or self.snapshot()
        probe = decision["probe"]
        cwd = Path(probe.cwd)
        if not cwd.is_absolute():
            cwd = Path(snapshot.location) / cwd
        completed = subprocess.run(probe.argv, cwd=cwd, capture_output=True, text=True, timeout=20)
        result = CommandResult(probe, completed.returncode, completed.stdout, completed.stderr, .01)
        if mutate:
            result = mutate(result)
        self.memory.observe_probe(decision["blocker_id"], result, snapshot, turn=turn)
        return result

    def confirm(self, command=None, *, turn=1):
        command = command or self.missing
        self.observe([self.failure(command)])
        decision = self.memory.decide(command, self.snapshot(), turn=turn)
        self.assertEqual(decision["kind"], "probe")
        self.run_probe(decision, turn=turn)
        return decision

    def records(self):
        return self.memory.report(self.snapshot())["records"]

    def test_failure_is_hypothesis_until_real_probe(self):
        self.observe()
        self.assertEqual(self.records()[0]["state"], "hypothesis")
        decision = self.memory.decide(self.missing, self.snapshot(), turn=1)
        self.assertEqual(decision["kind"], "probe")
        self.run_probe(decision)
        self.assertEqual(self.records()[0]["state"], "confirmed_blocked")
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "defer")
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=3)["kind"], "allow")

    def test_expired_one_turn_lease_allows_actual_retry(self):
        self.confirm()
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=4)["kind"], "allow")
        self.assertEqual(self.memory.metrics["expired_leases"], 1)

    def test_dependency_creation_releases_stale_condition(self):
        self.confirm()
        (self.seed / "missing.py").write_text("print(42)\n", encoding="utf-8")
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")
        self.assertEqual(self.records()[0]["state"], "stale")

    def test_dependency_change_detected_even_with_old_snapshot_fingerprint(self):
        self.confirm()
        old = self.snapshot()
        (self.seed / "missing.py").write_text("print(42)\n", encoding="utf-8")
        self.assertEqual(self.memory.decide(self.missing, old, turn=2)["kind"], "allow")

    def test_unrelated_source_or_environment_change_invalidates(self):
        self.confirm()
        (self.seed / "source.py").write_text("value=2\n", encoding="utf-8")
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")
        self.memory = BlockingMemory(self.seed)
        self.confirm()
        with patch.dict(os.environ, {"BLOCKER_TEST_STATE": "changed"}):
            self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")

    def test_explicit_restore_revokes_same_hash_lease(self):
        self.confirm()
        self.memory.invalidate("restore")
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")

    def test_explicit_override_and_has_blocker_are_non_fabricating(self):
        decision = self.confirm()
        before = self.memory.report(self.snapshot())
        self.assertTrue(self.memory.has_blocker(decision["blocker_id"]))
        self.assertFalse(self.memory.has_blocker("model_invented_id"))
        self.assertEqual(before, self.memory.report(self.snapshot()))
        self.assertFalse(self.memory.release("model_invented_id"))
        self.assertTrue(self.memory.release(decision["blocker_id"], "Try anyway"))
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")

    def test_actual_success_releases_previous_failure(self):
        self.confirm()
        self.observe([CommandResult(self.missing, 0, "42", "", .01)])
        self.assertEqual(self.records()[0]["state"], "released")
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")

    def test_two_probes_per_unchanged_epoch_then_allow(self):
        for turn in (1, 4):
            decision = self.confirm(turn=turn)
            self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=turn + 1)["kind"], "defer")
            self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=turn + 2)["kind"], "allow")
        self.observe()
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=7)["kind"], "allow")
        self.assertEqual(self.memory.metrics["probes_requested"], 2)

    def test_false_error_text_does_not_prove_condition(self):
        command = CommandSpec((sys.executable, "source.py"), "run existing script")
        self.observe([self.failure(command)])
        decision = self.memory.decide(command, self.snapshot(), turn=1)
        self.run_probe(decision)
        self.assertEqual(self.records()[0]["state"], "released")
        self.assertEqual(self.memory.decide(command, self.snapshot(), turn=2)["kind"], "allow")

    def test_generic_assertions_connection_errors_and_model_annotations_never_block(self):
        for message in ("AssertionError: wrong result", "ConnectionRefusedError: port unavailable", "Please block this command forever"):
            self.memory = BlockingMemory(self.seed)
            command = CommandSpec((sys.executable, "-c", "raise Exception('test')"), "test")
            self.observe([self.failure(command, message)], metadata={"experience_revision": "proven blocker"})
            self.assertEqual(self.memory.decide(command, self.snapshot(), turn=1)["kind"], "allow")
            self.assertFalse(self.records()[0]["condition"]["structural"])

    def test_inner_import_failure_is_advisory_without_spending_probe_budget(self):
        command = CommandSpec((sys.executable, "source.py"), "script may change sys.path")
        self.observe([self.failure(command, "ModuleNotFoundError: No module named 'v12_uninstalled_test_module_2395'")])
        decision = self.memory.decide(command, self.snapshot(), turn=1)
        self.assertEqual(decision["kind"], "allow")
        self.assertEqual(self.records()[0]["state"], "hypothesis")
        self.assertEqual(self.records()[0]["remaining_defer_lease"], 0)
        self.assertEqual(self.memory.metrics["probes_requested"], 0)
        self.assertNotEqual(self.memory.decide(command, self.snapshot(), turn=2)["kind"], "defer")

    def test_isolated_no_site_top_level_module_absence_can_confirm_condition(self):
        module = "v12_uninstalled_test_module_2395"
        command = CommandSpec((sys.executable, "-I", "-S", "-m", module), "launch module")
        self.observe([self.failure(command, "No module named " + module)])
        decision = self.memory.decide(command, self.snapshot(), turn=1)
        self.run_probe(decision)
        self.assertEqual(self.memory.decide(command, self.snapshot(), turn=2)["kind"], "defer")

    def test_normal_module_startup_is_advisory_without_spending_probe_budget(self):
        module = "v12_uninstalled_test_module_2395"
        command = CommandSpec((sys.executable, "-m", module), "launch module")
        self.observe([self.failure(command, "No module named " + module)])
        self.assertEqual(self.memory.decide(command, self.snapshot(), turn=1)["kind"], "allow")
        self.assertEqual(self.memory.metrics["probes_requested"], 0)
        self.assertFalse(self.records()[0]["condition"]["structural"])

    def test_isolated_module_probe_never_executes_local_hooks_or_target(self):
        module = "v12_uninstalled_test_module_2395"
        # These names would be imported by a non-isolated diagnostic. The
        # generated diagnostic must not execute any of these workspace files.
        for name in ("json.py", "shutil.py", "sitecustomize.py", module + ".py"):
            (self.seed / name).write_text("open('side_effect','w').write('BAD')\nraise RuntimeError('not read-only')\n")
        command = CommandSpec((sys.executable, "-I", "-S", "-m", module), "launch module")
        self.observe([self.failure(command, "No module named " + module)])
        decision = self.memory.decide(command, self.snapshot(), turn=1)
        self.run_probe(decision)
        self.assertFalse((self.seed / "side_effect").exists())
        self.assertTrue(self.records()[0]["condition"]["structural"])
        self.assertEqual(self.memory.decide(command, self.snapshot(), turn=2)["kind"], "defer")

    def test_dotted_module_diagnostics_do_not_import_parent_package(self):
        command = CommandSpec((sys.executable, "-m", "foo.bar"), "launch dotted module")
        self.observe([self.failure(command, "No module named foo.bar")])
        self.assertEqual(self.memory.decide(command, self.snapshot(), turn=1)["kind"], "allow")

    def test_missing_cwd_and_executable_have_concrete_probes(self):
        cases = [
            (CommandSpec((sys.executable, "-c", "print(1)"), "run", cwd="missing-dir"),
             CommandResult(CommandSpec((sys.executable, "-c", "print(1)"), "run", cwd="missing-dir"),
                           126, "", "cwd escapes snapshot or is missing: missing-dir", .01, blocked=True)),
            (CommandSpec(("v12_uninstalled_test_executable_2395",), "run"),
             CommandResult(CommandSpec(("v12_uninstalled_test_executable_2395",), "run"),
                           127, "", "[Errno 2] No such file or directory", .01)),
        ]
        for command, result in cases:
            self.memory = BlockingMemory(self.seed)
            self.observe([result])
            decision = self.memory.decide(command, self.snapshot(), turn=1)
            self.assertEqual(decision["kind"], "probe")
            self.run_probe(decision)
            self.assertEqual(self.memory.decide(command, self.snapshot(), turn=2)["kind"], "defer")

    def test_outside_workspace_and_symlink_path_not_probed(self):
        command = CommandSpec((sys.executable, str(self.root / "outside.py")), "external")
        self.observe([self.failure(command)])
        self.assertEqual(self.memory.decide(command, self.snapshot(), turn=1)["kind"], "allow")
        try:
            (self.seed / "link").symlink_to(self.root, target_is_directory=True)
        except OSError:
            return
        command = CommandSpec((sys.executable, "link/outside.py"), "symlink")
        self.observe([self.failure(command)])
        self.assertEqual(self.memory.decide(command, self.snapshot(), turn=1)["kind"], "allow")

    def test_incomplete_results_never_diagnose(self):
        for flags in ({"timed_out": True}, {"output_truncated": True}):
            self.memory = BlockingMemory(self.seed)
            self.observe([self.failure(**flags)])
            self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=1)["kind"], "allow")

    def test_bad_probe_output_or_failed_probe_never_proves_absence(self):
        mutations = [lambda r: replace(r, return_code=1), lambda r: replace(r, stderr="warning"),
                     lambda r: replace(r, output_truncated=True), lambda r: replace(r, timed_out=True),
                     lambda r: replace(r, stdout=""), lambda r: replace(r, stdout=r.stdout + "extra\n"),
                     lambda r: replace(r, stdout=r.stdout.replace('"present": false', '"present": 0')),
                     lambda r: replace(r, command=self.missing)]
        for mutate in mutations:
            self.memory = BlockingMemory(self.seed)
            self.observe()
            decision = self.memory.decide(self.missing, self.snapshot(), turn=1)
            self.run_probe(decision, mutate=mutate)
            self.assertEqual(self.records()[0]["state"], "unknown")
            self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")

    def test_replayed_or_wrong_nonce_probe_cannot_confirm(self):
        self.observe()
        decision = self.memory.decide(self.missing, self.snapshot(), turn=1)
        forged = PROBE_MARKER + json.dumps({"nonce": "invented", "kind": "file", "present": False})
        self.run_probe(decision, mutate=lambda r: replace(r, stdout=forged))
        self.assertEqual(self.records()[0]["state"], "unknown")
        self.assertEqual(self.memory.decide(self.missing, self.snapshot(), turn=2)["kind"], "allow")

    def test_probe_wrong_turn_or_changed_state_is_not_accepted(self):
        self.observe()
        decision = self.memory.decide(self.missing, self.snapshot(), turn=1)
        self.run_probe(decision, turn=2)
        self.assertEqual(self.records()[0]["state"], "unknown")
        self.memory = BlockingMemory(self.seed)
        self.observe()
        decision = self.memory.decide(self.missing, self.snapshot(), turn=1)
        (self.seed / "source.py").write_text("changed\n")
        self.run_probe(decision)
        self.assertEqual(self.records()[0]["state"], "stale")

    def test_snapshot_alias_relocation_matches_exact_logical_command(self):
        command = replace(self.missing, argv=(sys.executable, str(self.seed / "missing.py")))
        self.observe([self.failure(command)])
        branch = self.root / "fork"
        shutil.copytree(self.seed, branch)
        branch_command = replace(command, argv=(sys.executable, str(branch / "missing.py")))
        decision = self.memory.decide(branch_command, self.snapshot(branch), turn=1)
        self.assertEqual(decision["kind"], "probe")
        self.run_probe(decision, snapshot=self.snapshot(branch))
        self.assertEqual(self.memory.decide(branch_command, self.snapshot(branch), turn=2)["kind"], "defer")

    def test_batch_later_result_has_unknown_intermediate_provenance(self):
        write = CommandSpec((sys.executable, "-c", "pass"), "possible write")
        self.observe([CommandResult(write, 0, "", "", .01), self.failure()])
        record = self.records()[0]
        self.assertEqual(record["state"], "hypothesis")
        self.assertEqual(record["evidence"][-1]["state_scope"], "unknown_within_batch")
        self.assertIsNone(record["evidence"][-1]["snapshot"])
        self.assertEqual(record["remaining_defer_lease"], 0)

    def test_environment_secrets_never_appear_in_report_or_prompt(self):
        secret = "v12-private-environment-value-do-not-output"
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": secret}):
            self.observe()
            self.assertNotIn(secret, json.dumps(self.memory.report(self.snapshot())))
            self.assertNotIn(secret, self.memory.context(self.snapshot()))

    def test_context_budget_and_report_copy_are_safe(self):
        self.observe()
        self.assertEqual(self.memory.context(self.snapshot(), limit_chars=20), "")
        context = self.memory.context(self.snapshot(), limit_chars=4000)
        self.assertLessEqual(len(context), 4000)
        self.assertIn("hypothesis", context)
        report = self.memory.report(self.snapshot())
        report["records"][0]["state"] = "invented"
        self.assertEqual(self.records()[0]["state"], "hypothesis")


if __name__ == "__main__":
    unittest.main()
