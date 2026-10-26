import errno
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bestfgs.environment import EnvironmentConfig, ForkedWorkspaceEnvironment, _remove_verification_workspace
from bestfgs.models import CommandSpec, MacroAction


class EnvironmentTests(unittest.TestCase):
    def test_real_process_marks_truncated_stdout_or_stderr_without_changing_tails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            seed.mkdir()
            environment = ForkedWorkspaceEnvironment(seed, root / "runs", config=EnvironmentConfig(max_output_chars=8))
            snapshot = environment.initial_snapshot()
            for stdout, stderr, exit_code, expected in (
                ("0123456789abcdef", "short", 0, True),
                ("short", "0123456789abcdef", 2, True),
                ("12345678", "abcdefgh", 0, False),
                ("中文", "", 0, False),
            ):
                with self.subTest(stdout=stdout, stderr=stderr, exit_code=exit_code):
                    script = f"import sys; sys.stdout.write({stdout!r}); sys.stderr.write({stderr!r}); sys.exit({exit_code})"
                    action = MacroAction.create(name="emit_output", rationale="observe actual output limits",
                        semantic_direction_id="capture", semantic_direction_label="Capture",
                        commands=(CommandSpec((sys.executable, "-c", script), "emit output"),))
                    result, = environment.execute(snapshot, action, 1).command_results
                    self.assertEqual(result.return_code, exit_code)
                    self.assertEqual(result.stdout, stdout[-8:])
                    self.assertEqual(result.stderr, stderr[-8:])
                    self.assertIs(result.output_truncated, expected)

    def test_real_timeout_marks_truncated_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            seed.mkdir()
            environment = ForkedWorkspaceEnvironment(seed, root / "runs", config=EnvironmentConfig(max_output_chars=8))
            command = CommandSpec((sys.executable, "-c",
                "import sys,time; sys.stdout.write('stdout-0123456789'); sys.stdout.flush(); "
                "sys.stderr.write('stderr-9876543210'); sys.stderr.flush(); time.sleep(5)"),
                "emit output then exceed the bounded timeout", timeout_seconds=1)
            result, = environment.verify(environment.initial_snapshot(), (command,))
            self.assertTrue(result.timed_out)
            self.assertEqual(result.return_code, 124)
            self.assertEqual(result.stdout, "23456789")
            self.assertEqual(result.stderr, "76543210")
            self.assertTrue(result.output_truncated)

    def test_verification_cleans_readonly_git_objects_without_changing_seed_or_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            seed.mkdir()
            (seed / "main.py").write_text("value = 1\n", encoding="utf-8")
            def git(*args):
                subprocess.run(["git", *args], cwd=seed, capture_output=True, check=True)
            git("init")
            git("add", ".")
            git("-c", "user.name=VerificationTest", "-c", "user.email=test@example.org", "commit", "-m", "seed")
            environment = ForkedWorkspaceEnvironment(seed, root / "runs")
            snapshot = environment.initial_snapshot()
            candidate = Path(snapshot.location)
            def state(path):
                return {item.relative_to(path).as_posix(): (item.read_bytes(), item.stat().st_mode)
                        for item in path.rglob("*") if item.is_file()}
            seed_before, candidate_before = state(seed), state(candidate)
            if sys.platform == "win32":
                self.assertTrue(any(not item.stat().st_mode & stat.S_IWRITE
                                    for item in (candidate / ".git/objects").rglob("*") if item.is_file()))
            command = CommandSpec((sys.executable, "-c", "from pathlib import Path; assert Path('main.py').read_text().strip() == 'value = 1'"), "verify unchanged code")
            result = environment.verify(snapshot, (command,))
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0].succeeded)
            self.assertEqual(seed_before, state(seed))
            self.assertEqual(candidate_before, state(candidate))
            self.assertFalse(any((root / "runs").glob("final_verification_*")))

    def test_cleanup_never_accepts_run_root_or_external_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "runs"
            outside = root / "final_verification_external"
            runs.mkdir()
            outside.mkdir()
            with patch("bestfgs.environment.shutil.rmtree") as remove:
                for target in (runs, outside):
                    with self.assertRaises(ValueError):
                        _remove_verification_workspace(target, runs)
                remove.assert_not_called()

    def test_cleanup_readonly_retry_is_limited_to_its_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / "runs"
            target = runs / "final_verification_test"
            target.mkdir(parents=True)
            readonly = target / "object"
            readonly.write_text("git object")
            readonly.chmod(stat.S_IREAD)
            outside = root / "seed-object"
            outside.write_text("untouched")
            before = outside.stat().st_mode
            error = PermissionError(errno.EACCES, "read-only object")
            def reject_external(path, *, onerror):
                onerror(os.unlink, str(outside), (PermissionError, error, None))
            with patch("bestfgs.environment.sys.platform", "win32"), patch("bestfgs.environment.os.chmod") as chmod:
                with patch("bestfgs.environment.shutil.rmtree", side_effect=reject_external):
                    with self.assertRaises(ValueError):
                        _remove_verification_workspace(target, runs)
                chmod.assert_not_called()
            self.assertEqual(outside.read_text(), "untouched")
            self.assertEqual(outside.stat().st_mode, before)
            def retry_private(path, *, onerror):
                onerror(os.unlink, str(readonly), (PermissionError, error, None))
            with patch("bestfgs.environment.sys.platform", "win32"), patch("bestfgs.environment.shutil.rmtree", side_effect=retry_private):
                _remove_verification_workspace(target, runs)
            self.assertFalse(readonly.exists())

    def test_cleanup_does_not_swallow_other_io_or_acl_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "runs" / "final_verification_test"
            target.mkdir(parents=True)
            file = target / "writable"
            file.write_text("value")
            for error in (OSError(errno.EIO, "disk I/O error"), PermissionError(errno.EACCES, "ACL denied")):
                def fail(path, *, onerror):
                    onerror(os.unlink, str(file), (type(error), error, None))
                with patch("bestfgs.environment.sys.platform", "win32"), patch("bestfgs.environment.os.chmod") as chmod:
                    with patch("bestfgs.environment.shutil.rmtree", side_effect=fail):
                        with self.assertRaises(type(error)) as caught:
                            _remove_verification_workspace(target, target.parent)
                    self.assertIs(caught.exception, error)
                    chmod.assert_not_called()

    def test_cleanup_permission_retry_refuses_link_even_when_target_is_inside(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "runs" / "final_verification_test"
            target.mkdir(parents=True)
            linked = target / "link"
            linked.write_text("do not chmod through a link")
            actual_lstat = Path.lstat
            def link_stat(path):
                if path == linked:
                    return SimpleNamespace(st_mode=stat.S_IFLNK | stat.S_IREAD, st_file_attributes=0)
                return actual_lstat(path)
            error = PermissionError(errno.EACCES, "read-only link")
            def fail(path, *, onerror):
                with patch.object(Path, "lstat", link_stat):
                    onerror(os.unlink, str(linked), (PermissionError, error, None))
            with patch("bestfgs.environment.sys.platform", "win32"), patch("bestfgs.environment.os.chmod") as chmod:
                with patch("bestfgs.environment.shutil.rmtree", side_effect=fail):
                    with self.assertRaisesRegex(ValueError, "through a link"):
                        _remove_verification_workspace(target, target.parent)
                chmod.assert_not_called()
            self.assertEqual(linked.read_text(), "do not chmod through a link")

    def test_verification_artifacts_do_not_enter_submission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            seed.mkdir()
            env = ForkedWorkspaceEnvironment(seed, root / "runs")
            action = MacroAction.create(
                name="polyglot", rationale="deliver one source file",
                semantic_direction_id="implement", semantic_direction_label="implement",
                intent="candidate",
                commands=(CommandSpec((sys.executable, "-c",
                    "from pathlib import Path; Path('main.py.c').write_text('source')"), "create source"),),
                verification_commands=(CommandSpec((sys.executable, "-c",
                    "from pathlib import Path; assert Path('main.py.c').read_text() == 'source'; "
                    "Path('cmain').write_text('compiled')"), "compile in disposable test copy"),),
            )
            outcome = env.execute(env.initial_snapshot(), action, 2)
            self.assertTrue(outcome.functional_validation_succeeded)
            self.assertEqual(outcome.tool_call_count, 2)
            self.assertEqual([p.name for p in Path(outcome.resulting_snapshot.location).iterdir()], ["main.py.c"])
            self.assertTrue(env.verify(outcome.resulting_snapshot, action.verification_commands)[0].succeeded)
            self.assertFalse((Path(outcome.resulting_snapshot.location) / "cmain").exists())

    def test_verification_cannot_fix_candidate_and_then_claim_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            seed.mkdir()
            (seed / "value.txt").write_text("wrong", encoding="utf-8")
            env = ForkedWorkspaceEnvironment(seed, root / "runs", config=EnvironmentConfig(max_output_chars=8))
            snapshot = env.initial_snapshot()
            check = CommandSpec((sys.executable, "-c",
                "from pathlib import Path; Path('value.txt').write_text('right'); "
                "assert Path('value.txt').read_text() == 'right'; print('x' * 32)"), "dishonest verification")
            result = env.verify(snapshot, (check,))[0]
            self.assertFalse(result.succeeded)
            self.assertIn("modified candidate", result.stderr)
            self.assertTrue(result.output_truncated)  # validation's replace preserves capture metadata
            self.assertEqual((Path(snapshot.location) / "value.txt").read_text(), "wrong")

    def test_snapshot_metadata_tracks_modified_and_deleted_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            seed.mkdir()
            (seed / "kept.txt").write_text("old", encoding="utf-8")
            (seed / "removed.txt").write_text("remove", encoding="utf-8")
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            action = MacroAction.create(
                name="change_two_files",
                rationale="exercise evidence freshness metadata",
                semantic_direction_id="file_state",
                semantic_direction_label="File state",
                commands=(
                    CommandSpec(
                        (
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('kept.txt').write_text('new'); Path('removed.txt').unlink()",
                        ),
                        "modify kept.txt and remove removed.txt",
                    ),
                ),
            )

            outcome = environment.execute(snapshot, action, 1)

            expected = ("kept.txt", "removed.txt")
            self.assertEqual(outcome.changed_workspace_paths, expected)
            self.assertEqual(
                tuple(outcome.resulting_snapshot.metadata["changed_paths_from_root"]),
                expected,
            )

    @unittest.skipUnless(sys.platform == "win32", "cmd.exe encoding regression is Windows-only")
    def test_cmd_type_reads_utf8_readme_without_gbk_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            seed.mkdir()
            (seed / "README.md").write_text("中文需求与€符号", encoding="utf-8")
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            action = MacroAction.create(
                name="read_readme",
                rationale="reproduce the original Windows command",
                semantic_direction_id="readme_requirements",
                semantic_direction_label="README requirements",
                commands=(
                    CommandSpec(
                        ("cmd.exe", "/d", "/s", "/c", "type README.md"),
                        "display README.md",
                    ),
                ),
            )

            outcome = environment.execute(snapshot, action, 1)

            result = outcome.command_results[0]
            self.assertTrue(result.succeeded)
            self.assertIn("中文需求", result.stdout)
            self.assertIn("€", result.stdout)

    def test_utf8_and_invalid_process_output_never_crashes_reader(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            seed.mkdir()
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            script = (
                "import sys; "
                "sys.stdout.buffer.write('中文与€'.encode('utf-8')); "
                "sys.stderr.buffer.write(bytes([128]) + b'broken')"
            )
            action = MacroAction.create(
                name="emit_bytes",
                rationale="exercise byte-safe subprocess capture",
                semantic_direction_id="output_encoding",
                semantic_direction_label="Process output encoding",
                commands=(
                    CommandSpec((sys.executable, "-c", script), "emit mixed output bytes"),
                ),
            )

            outcome = environment.execute(snapshot, action, 1)

            result = outcome.command_results[0]
            self.assertEqual(result.stdout, "中文与€")
            self.assertIn("broken", result.stderr)
            self.assertEqual(result.return_code, 0)

    def test_edge_execution_does_not_modify_seed_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            seed.mkdir()
            (seed / "value.txt").write_text("seed", encoding="utf-8")
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            action = MacroAction.create(
                name="edit",
                rationale="test isolation",
                semantic_direction_id="edit-value",
                semantic_direction_label="Edit the value",
                commands=(
                    CommandSpec(
                        (
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('value.txt').write_text('child')",
                        ),
                        "write the child value",
                    ),
                ),
            )
            outcome = environment.execute(snapshot, action, 1)
            self.assertTrue(outcome.commands_succeeded, outcome.observation_text())
            self.assertEqual((seed / "value.txt").read_text(encoding="utf-8"), "seed")
            child = Path(outcome.resulting_snapshot.location)
            self.assertEqual((child / "value.txt").read_text(encoding="utf-8"), "child")

    def test_candidate_runs_independent_functional_verification_and_can_replay_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            seed.mkdir()
            (seed / "value.txt").write_text("seed", encoding="utf-8")
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            verification = CommandSpec(
                (
                    sys.executable,
                    "-c",
                    "from pathlib import Path; assert Path('value.txt').read_text() == 'fixed'",
                ),
                "verify the fixed behavior",
            )
            action = MacroAction.create(
                name="write_verified_candidate",
                rationale="exercise candidate verification",
                semantic_direction_id="functional_verification",
                semantic_direction_label="Functional verification",
                commands=(
                    CommandSpec(
                        (
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('value.txt').write_text('fixed')",
                        ),
                        "write candidate",
                    ),
                ),
                verification_commands=(verification,),
                intent="candidate",
            )

            outcome = environment.execute(snapshot, action, 2)
            replay = environment.verify(outcome.resulting_snapshot, (verification,))

            self.assertTrue(outcome.functional_validation_attempted)
            self.assertTrue(outcome.functional_validation_succeeded)
            self.assertEqual(outcome.tool_call_count, 2)
            self.assertTrue(replay and replay[0].succeeded)
            self.assertFalse(any(runs.glob("final_verification_*")))

    def test_modified_python_with_invalid_syntax_fails_automatic_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            seed.mkdir()
            (seed / "module.py").write_text("value = 1\n", encoding="utf-8")
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            action = MacroAction.create(
                name="break_python",
                rationale="exercise the validation gate",
                semantic_direction_id="repair",
                semantic_direction_label="Repair",
                commands=(
                    CommandSpec(
                        (
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('module.py').write_text('if broken:\\n')",
                        ),
                        "write syntactically invalid Python",
                    ),
                ),
            )

            outcome = environment.execute(snapshot, action, 1)

            self.assertTrue(outcome.commands_succeeded)
            self.assertFalse(outcome.validation_succeeded)
            self.assertRegex(
                outcome.validation_results[0].stderr,
                r"(?:Syntax|Indentation)Error",
            )
            self.assertIn("internal-validation-gate", outcome.observation_text())

    def test_seed_workspace_alias_is_mapped_to_current_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            seed.mkdir()
            (seed / "value.txt").write_text("seed", encoding="utf-8")
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            aliased_file = (seed / "value.txt").as_posix()
            script = (
                "import os; from pathlib import Path; "
                "assert Path(os.environ['RETRAC_WORKSPACE']).resolve() == Path.cwd(); "
                f"Path({aliased_file!r}).write_text('snapshot', encoding='utf-8')"
            )
            action = MacroAction.create(
                name="edit_through_workspace_alias",
                rationale="benchmark paths such as /app must stay branch-local",
                semantic_direction_id="workspace_alias",
                semantic_direction_label="Workspace alias",
                commands=(
                    CommandSpec(
                        (sys.executable, "-c", script),
                        "write through the original workspace path",
                        cwd=str(seed),
                    ),
                ),
            )

            outcome = environment.execute(snapshot, action, 1)

            self.assertTrue(outcome.commands_succeeded, outcome.observation_text())
            self.assertEqual((seed / "value.txt").read_text(encoding="utf-8"), "seed")
            child = Path(outcome.resulting_snapshot.location)
            self.assertEqual((child / "value.txt").read_text(encoding="utf-8"), "snapshot")

    def test_absolute_cwd_outside_seed_workspace_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed"
            runs = root / "runs"
            outside = root / "outside"
            seed.mkdir()
            outside.mkdir()
            environment = ForkedWorkspaceEnvironment(seed, runs)
            snapshot = environment.initial_snapshot()
            action = MacroAction.create(
                name="escape",
                rationale="verify the alias does not weaken isolation",
                semantic_direction_id="workspace_safety",
                semantic_direction_label="Workspace safety",
                commands=(
                    CommandSpec((sys.executable, "-c", "print('unsafe')"), "escape", cwd=str(outside)),
                ),
            )

            outcome = environment.execute(snapshot, action, 1)

            result = outcome.command_results[0]
            self.assertTrue(result.blocked)
            self.assertEqual(result.return_code, 126)


if __name__ == "__main__":
    unittest.main()
