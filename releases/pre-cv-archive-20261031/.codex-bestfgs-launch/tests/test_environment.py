import sys
import tempfile
import unittest
from pathlib import Path

from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.models import CommandSpec, MacroAction


class EnvironmentTests(unittest.TestCase):
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
            env = ForkedWorkspaceEnvironment(seed, root / "runs")
            snapshot = env.initial_snapshot()
            check = CommandSpec((sys.executable, "-c",
                "from pathlib import Path; Path('value.txt').write_text('right'); "
                "assert Path('value.txt').read_text() == 'right'"), "dishonest verification")
            result = env.verify(snapshot, (check,))[0]
            self.assertFalse(result.succeeded)
            self.assertIn("modified candidate", result.stderr)
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
