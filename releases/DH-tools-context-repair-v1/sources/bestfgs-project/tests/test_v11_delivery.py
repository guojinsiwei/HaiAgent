"""Regression fixtures for checking the artifact that will actually be delivered."""
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.environment import ForkedWorkspaceEnvironment, _tree_fingerprint, _tree_manifest
from bestfgs.models import CommandSpec, MacroAction
from bestfgs.submission import (
    SubmissionError, inspect_git_submission, materialize_git_submission, resolve_git_base,
)


class VerificationImmutabilityV11Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "answer.py").write_text("answer = 0\n", encoding="utf-8")
        self.environment = ForkedWorkspaceEnvironment(self.seed, self.root / "runs")
        self.snapshot = self.environment.initial_snapshot()

    def command(self, code):
        return CommandSpec((sys.executable, "-c", "from pathlib import Path; " + code), "fixture")

    def test_verification_cannot_recreate_a_deleted_candidate_source(self):
        action = MacroAction.create(name="delete", rationale="fixture", semantic_direction_id="fixture",
            semantic_direction_label="fixture", commands=(self.command("Path('answer.py').unlink()"),))
        candidate = self.environment.execute(self.snapshot, action, 1).resulting_snapshot
        check = self.command("Path('answer.py').write_text('answer = 42\\n'); import answer; assert answer.answer == 42")
        result, = self.environment.verify(candidate, (check,))
        self.assertFalse(result.succeeded)
        self.assertIn("answer.py", result.stderr)
        self.assertFalse((Path(candidate.location) / "answer.py").exists())
        self.assertEqual((self.seed / "answer.py").read_text(), "answer = 0\n")

    def test_new_source_is_a_mutation_even_when_check_exits_zero(self):
        result, = self.environment.verify(self.snapshot, (
            self.command("Path('new_module.py').write_text('value = 42\\n')"),))
        self.assertFalse(result.succeeded)
        self.assertIn("new_module.py", result.stderr)
        self.assertFalse((Path(self.snapshot.location) / "new_module.py").exists())

    def test_unknown_outputs_are_not_silently_classified_as_generated(self):
        result, = self.environment.verify(self.snapshot, (
            self.command("Path('answer').write_text('#!/bin/sh\\necho fake-pass\\n')"),))
        self.assertFalse(result.succeeded)
        self.assertIn("answer", result.stderr)

    def test_deletion_and_overwrite_are_mutations(self):
        for code in ("Path('answer.py').unlink()", "Path('answer.py').write_text('answer = 42\\n')"):
            with self.subTest(code=code):
                result, = self.environment.verify(self.snapshot, (self.command(code),))
                self.assertFalse(result.succeeded)
                self.assertIn("answer.py", result.stderr)

    def test_known_caches_and_explicit_outputs_are_disposable(self):
        code = (
            "paths = ['.pytest_cache/v/cache/nodeids', '__pycache__/answer.pyc', "
            "'.mypy_cache/cache.json', '.ruff_cache/cache.bin', '.coverage', '.coverage.worker', "
            "'.bestfgs_verify_outputs/report.xml', '.bestfgs_verify_outputs/compiled']; "
            "[(Path(p).parent.mkdir(parents=True, exist_ok=True), Path(p).write_text('generated')) for p in paths]"
        )
        result, = self.environment.verify(self.snapshot, (self.command(code),))
        self.assertTrue(result.succeeded, result.stderr)
        self.assertEqual([p.name for p in Path(self.snapshot.location).iterdir()], ["answer.py"])
        self.assertFalse(list((self.root / "runs").glob("final_verification_*")))

    def test_coverage_configuration_is_not_coverage_output(self):
        result, = self.environment.verify(self.snapshot, (
            self.command("Path('.coveragerc').write_text('[run]\\nomit = *\\n')"),))
        self.assertFalse(result.succeeded)
        self.assertIn(".coveragerc", result.stderr)

    def test_empty_verification_does_not_copy_or_scan(self):
        with patch("bestfgs.environment._copy_workspace") as copy, patch("bestfgs.environment._verification_manifest") as scan:
            self.assertEqual(self.environment.verify(self.snapshot, ()), ())
        copy.assert_not_called()
        scan.assert_not_called()

    def test_tool_environment_does_not_receive_controller_api_keys(self):
        names = ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DASHSCOPE_API_KEY")
        environment = {name: "fixture-controller-value" for name in names}
        environment["BESTFGS_TASK_FIXTURE_CREDENTIAL"] = "fixture-task-value"
        check = self.command(
            f"import os; assert all(name not in os.environ for name in {names!r}); "
            "assert os.environ['BESTFGS_TASK_FIXTURE_CREDENTIAL'] == 'fixture-task-value'"
        )
        with patch.dict(os.environ, environment):
            result, = self.environment.verify(self.snapshot, (check,))
            self.assertTrue(result.succeeded, result.stderr)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "fixture-controller-value")

    def test_custom_controller_credential_can_also_be_withheld(self):
        self.environment.config.controller_credential_variables += ("CUSTOM_MODEL_SECRET",)
        with patch.dict(os.environ, {"CUSTOM_MODEL_SECRET": "fixture-only"}):
            result, = self.environment.verify(self.snapshot, (self.command(
                "import os; assert 'CUSTOM_MODEL_SECRET' not in os.environ"),))
        self.assertTrue(result.succeeded, result.stderr)

    def test_old_snapshot_absolute_path_targets_the_new_child_only(self):
        old_path = (Path(self.snapshot.location) / "answer.py").as_posix()
        action = MacroAction.create(name="fix", rationale="fixture", semantic_direction_id="fixture",
            semantic_direction_label="fixture", commands=(self.command(
                f"Path({old_path!r}).write_text('answer = 42\\n')"),))
        outcome = self.environment.execute(self.snapshot, action, 1)
        self.assertTrue(outcome.commands_succeeded)
        self.assertEqual((Path(self.snapshot.location) / "answer.py").read_text(), "answer = 0\n")
        self.assertEqual((self.seed / "answer.py").read_text(), "answer = 0\n")
        self.assertEqual((Path(outcome.resulting_snapshot.location) / "answer.py").read_text(), "answer = 42\n")
        check = self.command(f"assert Path({old_path!r}).read_text().strip() == 'answer = 42'")
        result, = self.environment.verify(outcome.resulting_snapshot, (check,))
        self.assertTrue(result.succeeded, result.stderr)

    def test_prior_snapshot_alias_requires_a_complete_path_prefix(self):
        old = Path(self.snapshot.location).as_posix()
        unrelated = old + "_different/answer.py"
        child = self.root / "runs" / "child"
        self.assertEqual(self.environment._rewrite_workspace_references(unrelated, child), unrelated)

    def test_snapshot_fingerprint_accounts_for_executable_mode(self):
        before = _tree_fingerprint(self.seed)
        original = Path.lstat
        def changed_mode(path):
            result = original(path)
            if path.name == "answer.py":
                return os.stat_result((result.st_mode ^ 0o111, *tuple(result)[1:]))
            return result
        with patch.object(Path, "lstat", changed_mode):
            self.assertNotEqual(_tree_fingerprint(self.seed), before)

    def test_snapshot_fingerprint_tracks_link_identity_without_following_target(self):
        original = Path.lstat
        def link_mode(path):
            result = original(path)
            if path.name == "answer.py":
                return os.stat_result((stat.S_IFLNK | 0o777, *tuple(result)[1:]))
            return result
        with patch.object(Path, "lstat", link_mode), patch("bestfgs.environment.os.readlink", return_value="/private/external"), patch("bestfgs.environment._file_digest") as read:
            value = _tree_manifest(self.seed)["answer.py"]
        self.assertTrue(value[1].startswith("link:"))
        read.assert_not_called()

    @unittest.skipIf(os.name == "nt", "POSIX executable-bit semantics")
    def test_executable_mode_change_is_a_mutation(self):
        result, = self.environment.verify(self.snapshot, (self.command("Path('answer.py').chmod(0o755)"),))
        self.assertFalse(result.succeeded)
        self.assertIn("answer.py", result.stderr)


class CleanDeliveryV11Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        self.git("init")
        self.git("config", "core.autocrlf", "false")
        (self.seed / "answer.py").write_text("answer = 0\n", encoding="utf-8")
        (self.seed / "deleted.py").write_text("old = True\n", encoding="utf-8")
        (self.seed / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base")
        self.base = resolve_git_base(self.seed)

    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.seed, capture_output=True, check=True).stdout

    def test_base_plus_patch_reproduces_selected_tree_and_new_files(self):
        (self.seed / "answer.py").write_text("answer = 42\n", encoding="utf-8")
        (self.seed / "deleted.py").unlink()
        (self.seed / "new.py").write_text("value = 7\n", encoding="utf-8")
        (self.seed / "data.bin").write_bytes(bytes(range(256)))
        (self.seed / "ignored.py").write_text("not delivered\n", encoding="utf-8")
        target = self.root / "delivered"
        exported = materialize_git_submission(self.seed, self.base, target)
        rebuilt = inspect_git_submission(target, self.base)
        self.assertEqual(exported.patch, rebuilt.patch)
        self.assertEqual(exported.tree_id, rebuilt.tree_id)
        self.assertEqual(resolve_git_base(target), self.base)
        self.assertEqual((target / "answer.py").read_text(), "answer = 42\n")
        self.assertEqual((target / "new.py").read_text(), "value = 7\n")
        self.assertEqual((target / "data.bin").read_bytes(), bytes(range(256)))
        self.assertFalse((target / "deleted.py").exists())
        self.assertFalse((target / "ignored.py").exists())
        self.assertFalse((target / ".git/objects/info/alternates").exists())

    def test_explicitly_staged_ignored_source_is_reproducible(self):
        (self.seed / "ignored.py").write_text("value = 7\n", encoding="utf-8")
        self.git("add", "-f", "ignored.py")
        target = self.root / "delivered"
        exported = materialize_git_submission(self.seed, self.base, target)
        self.assertIn("ignored.py", exported.changed_paths)
        self.assertEqual((target / "ignored.py").read_text(), "value = 7\n")

    def test_explicit_exclusions_do_not_leak_into_delivery(self):
        (self.seed / "scratch.py").write_text("assert False\n", encoding="utf-8")
        (self.seed / "answer.py").write_text("answer = 42\n", encoding="utf-8")
        target = self.root / "delivered"
        exported = materialize_git_submission(self.seed, self.base, target, excluded_paths=("scratch.py",))
        self.assertEqual(exported.changed_paths, ("answer.py",))
        self.assertFalse((target / "scratch.py").exists())

    def test_reserved_verification_outputs_are_not_a_submission(self):
        output = self.seed / ".bestfgs_verify_outputs/report.xml"
        output.parent.mkdir()
        output.write_text("<testsuite/>\n", encoding="utf-8")
        exported = materialize_git_submission(self.seed, self.base, self.root / "delivered")
        self.assertFalse(exported.has_changes)
        self.assertFalse((self.root / "delivered/.bestfgs_verify_outputs").exists())

    def test_selected_candidate_with_new_head_uses_original_base(self):
        (self.seed / "answer.py").write_text("answer = 42\n", encoding="utf-8")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "candidate")
        target = self.root / "delivered"
        exported = materialize_git_submission(self.seed, self.base, target)
        self.assertIn(b"-answer = 0", exported.patch)
        self.assertEqual(resolve_git_base(target), self.base)

    def test_empty_patch_rebuilds_base_without_claiming_changes(self):
        target = self.root / "delivered"
        exported = materialize_git_submission(self.seed, self.base, target)
        self.assertFalse(exported.has_changes)
        self.assertEqual((target / "answer.py").read_text(), "answer = 0\n")

    def test_existing_target_is_never_overwritten(self):
        target = self.root / "delivered"
        target.mkdir()
        (target / "important.txt").write_text("preserve")
        with self.assertRaisesRegex(SubmissionError, "already exists"):
            materialize_git_submission(self.seed, self.base, target)
        self.assertEqual((target / "important.txt").read_text(), "preserve")

    def test_target_inside_candidate_is_rejected_before_creation(self):
        with self.assertRaisesRegex(SubmissionError, "outside"):
            materialize_git_submission(self.seed, self.base, self.seed / "delivered")
        self.assertFalse((self.seed / "delivered").exists())

    def test_escaping_symlink_is_rejected_before_creation(self):
        outside = self.root / "outside.txt"
        outside.write_text("private")
        link = self.seed / "external.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")
        target = self.root / "delivered"
        with self.assertRaisesRegex(SubmissionError, "escaping symlink"):
            materialize_git_submission(self.seed, self.base, target)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
