import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.submission import (
    SubmissionError, export_git_submission, inspect_git_submission, resolve_git_base,
)


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        self.git("init")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "user.name", "Submission Test")
        self.git("config", "user.email", "test@example.org")
        (self.seed / "main.py").write_text("value = 1\n", encoding="utf-8")
        (self.seed / "deleted.py").write_text("old = True\n", encoding="utf-8")
        (self.seed / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.base = resolve_git_base(self.seed)

    def git(self, *args, cwd=None):
        return subprocess.run(
            ["git", *args], cwd=cwd or self.seed,
            capture_output=True, check=True,
        ).stdout

    def metadata(self):
        return {path.relative_to(self.seed).as_posix(): path.read_bytes()
                for path in (self.seed / ".git").rglob("*") if path.is_file()}

    def test_final_tree_includes_staged_unstaged_deleted_and_new_without_git_writes(self):
        (self.seed / "main.py").write_text("value = 2\n", encoding="utf-8")
        self.git("add", "main.py")
        (self.seed / "main.py").write_text("value = 3\n", encoding="utf-8")
        (self.seed / "deleted.py").unlink()
        (self.seed / "new.py").write_text("created = True\n", encoding="utf-8")
        (self.seed / "ignored.py").write_text("explicitly_staged = True\n", encoding="utf-8")
        self.git("add", "-f", "ignored.py")
        before = self.metadata()
        result = inspect_git_submission(self.seed, self.base)
        self.assertTrue(result.has_changes)
        self.assertEqual(set(result.changed_paths), {"main.py", "deleted.py", "new.py", "ignored.py"})
        self.assertIn(b"+value = 3", result.patch)
        self.assertNotIn(b"+value = 2", result.patch)
        self.assertEqual(before, self.metadata())

    def test_metadata_and_caches_do_not_create_a_deliverable(self):
        (self.seed / ".git" / "agent-marker").write_text("metadata changed")
        for relative in ("__pycache__/noise.pyc", "pkg/__pycache__/noise.pyc", ".bestfgs_runs/verify.py"):
            target = self.seed / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"not source")
        result = inspect_git_submission(self.seed, self.base)
        self.assertFalse(result.has_changes)
        self.assertEqual(result.patch, b"")
        self.assertEqual(result.changed_paths, ())

    def test_explicit_artifact_exclusion_does_not_guess_source_file_names(self):
        (self.seed / "verification.py").write_text("print('source deliverable')\n")
        (self.seed / "scratch.py").write_text("print('owned scratch')\n")
        result = inspect_git_submission(self.seed, self.base, excluded_paths=("scratch.py",))
        self.assertEqual(result.changed_paths, ("verification.py",))
        self.assertTrue((self.seed / "scratch.py").exists())

    def test_copy_and_changed_head_still_compare_to_original_task_base(self):
        candidate = self.root / "snapshot"
        shutil.copytree(self.seed, candidate, symlinks=True)
        (candidate / "main.py").write_text("value = 9\n", encoding="utf-8")
        self.git("add", "main.py", cwd=candidate)
        self.git("commit", "-m", "candidate", cwd=candidate)
        self.assertNotEqual(resolve_git_base(candidate), self.base)
        result = inspect_git_submission(candidate, self.base)
        self.assertTrue(result.has_changes)
        self.assertIn(b"-value = 1", result.patch)
        self.assertIn(b"+value = 9", result.patch)
        self.assertFalse(inspect_git_submission(self.seed, self.base).has_changes)

    def test_worktree_git_file_is_read_only_even_in_copied_snapshot(self):
        linked = self.root / "linked"
        self.git("worktree", "add", "--detach", str(linked), self.base)
        candidate = self.root / "copied-linked"
        shutil.copytree(linked, candidate, symlinks=True)
        (candidate / "main.py").write_text("value = 7\n", encoding="utf-8")
        before = self.metadata()
        self.assertEqual(resolve_git_base(candidate), self.base)
        result = inspect_git_submission(candidate, self.base)
        self.assertIn(b"+value = 7", result.patch)
        self.assertEqual((linked / "main.py").read_text(), "value = 1\n")
        self.assertEqual(before, self.metadata())

    def test_symlink_is_exported_as_link_not_target_contents(self):
        outside = self.root / "outside.txt"
        outside.write_text("PRIVATE TARGET CONTENT")
        link = self.seed / "linked.txt"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Symlink creation is unavailable: {exc}")
        result = inspect_git_submission(self.seed, self.base)
        self.assertIn("linked.txt", result.changed_paths)
        self.assertIn(b"new file mode 120000", result.patch)
        self.assertNotIn(b"PRIVATE TARGET CONTENT", result.patch)

    def test_no_enclosing_git_discovery(self):
        child = self.seed / "nested-task"
        child.mkdir()
        self.assertIsNone(resolve_git_base(child))
        with self.assertRaisesRegex(SubmissionError, "no task-local"):
            inspect_git_submission(child, self.base)

    def test_invalid_git_or_base_fails_closed(self):
        with self.assertRaises(SubmissionError):
            inspect_git_submission(self.seed, "0" * 40)
        with self.assertRaisesRegex(SubmissionError, "immutable"):
            inspect_git_submission(self.seed, "HEAD")
        broken = self.root / "broken"
        broken.mkdir()
        (broken / ".git").write_text("gitdir: missing\n")
        with self.assertRaises(SubmissionError):
            resolve_git_base(broken)
        with patch("bestfgs.submission.subprocess.run", side_effect=OSError("git unavailable")):
            with self.assertRaisesRegex(SubmissionError, "unavailable"):
                inspect_git_submission(self.seed, self.base)

    def test_export_preserves_bytes_and_never_writes_into_candidate(self):
        (self.seed / "binary.bin").write_bytes(bytes(range(256)))
        artifact = self.root / "model.patch"
        result = export_git_submission(self.seed, self.base, artifact)
        self.assertEqual(artifact.read_bytes(), result.patch)
        self.assertIn(b"GIT binary patch", result.patch)
        with self.assertRaisesRegex(SubmissionError, "outside"):
            export_git_submission(self.seed, self.base, self.seed / "model.patch")
        self.assertFalse((self.seed / "model.patch").exists())

    def test_inherited_git_environment_cannot_redirect_inspection(self):
        elsewhere = self.root / "elsewhere.index"
        with patch.dict(os.environ, {"GIT_WORK_TREE": str(self.root), "GIT_INDEX_FILE": str(elsewhere)}):
            self.assertFalse(inspect_git_submission(self.seed, self.base).has_changes)
        self.assertFalse(elsewhere.exists())


if __name__ == "__main__":
    unittest.main()
