from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.evidence_memory import EvidenceMemory
from bestfgs.models import CommandResult, CommandSpec, EnvironmentSnapshot, ExecutionOutcome, MacroAction


class EvidenceMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "source.py").write_text("value = 1\n", encoding="utf-8")
        (self.seed / "other.py").write_text("other = 1\n", encoding="utf-8")
        self.memory = EvidenceMemory(self.seed)
        # No dependence on POSIX executables being installed on Windows; these
        # tests use recorded real-command-shaped observations and fake lookup.
        self.lookup = patch("bestfgs.evidence_memory.shutil.which", return_value=sys.executable)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def snapshot(self, path=None):
        path = path or self.seed
        digest = hashlib.sha256()
        for file in sorted(path.rglob("*")):
            if file.is_file():
                digest.update(file.relative_to(path).as_posix().encode())
                digest.update(file.read_bytes())
        return EnvironmentSnapshot(path.name, str(path), digest.hexdigest(), "test")

    def branch(self, name, **changes):
        path = self.root / name
        shutil.copytree(self.seed, path)
        for filename, content in changes.items():
            (path / filename).write_text(content, encoding="utf-8")
        return self.snapshot(path)

    def command(self, *args, cwd=".", stdin=None):
        return CommandSpec(tuple(args), "recorded test command", cwd=cwd, stdin=stdin)

    def observe(self, commands=(), *, verification=(), results=None, verification_results=None, before=None, after=None):
        before = before or self.snapshot()
        after = after or before
        action = MacroAction.create(name="test", rationale="test", semantic_direction_id="test",
                                    semantic_direction_label="test", commands=tuple(commands),
                                    verification_commands=tuple(verification))
        results = results if results is not None else tuple(CommandResult(command, 0, "value = 1\n", "", 0.01) for command in commands)
        verification_results = verification_results if verification_results is not None else tuple(CommandResult(command, 1, "", "AssertionError: exact failure", 0.01) for command in verification)
        outcome = ExecutionOutcome(before, after, action, tuple(results), functional_validation_results=tuple(verification_results))
        self.memory.observe(action, outcome, before)

    def test_exact_explicit_read_reused_across_snapshots_and_seed_alias(self):
        command = self.command("cat", str(self.seed / "source.py"))
        self.observe((command,))
        branch = self.branch("fork", **{"other.py": "unrelated = 2\n"})
        hit = self.memory.check_command(self.command("cat", str(Path(branch.location) / "source.py")), branch)
        self.assertIsNotNone(hit)
        self.assertTrue(hit["cached"])
        self.assertEqual(hit["stdout"], "value = 1\n")
        self.assertEqual(hit["dependencies"], ["source.py"])
        self.assertEqual(self.memory.metrics["cache_hits"], 1)

    def test_changed_dependency_allows_real_execution(self):
        command = self.command("cat", "source.py")
        self.observe((command,))
        branch = self.branch("changed", **{"source.py": "value = 2\n"})
        self.assertIsNone(self.memory.check_command(command, branch))
        self.assertEqual(self.memory.metrics["cache_invalidations"], 1)

    def test_content_revert_can_reuse_exact_old_read(self):
        command = self.command("head", "-n", "20", "source.py")
        self.observe((command,))
        changed = self.branch("changed", **{"source.py": "value = 2\n"})
        self.assertIsNone(self.memory.check_command(command, changed))
        self.assertIsNotNone(self.memory.check_command(command, self.snapshot()))

    def test_unknown_and_unsafe_commands_never_cache(self):
        commands = [self.command("python", "-c", "print(open('source.py').read())"),
                    self.command("sh", "-c", "cat source.py"), self.command("tail", "-f", "source.py"),
                    self.command("rg", "value", "."), self.command("cat", "-"),
                    self.command("cat", "source.py", stdin="not empty"),
                    self.command("cat", str(self.root / "outside.txt")),
                    self.command("head", "source.py", "other.py"),
                    self.command("rg", "--pre", "evil", "value", "source.py")]
        for command in commands:
            self.observe((command,))
            self.assertIsNone(self.memory.check_command(command, self.snapshot()), command)

    def test_rg_pattern_is_not_treated_as_a_path(self):
        command = self.command("rg", "--no-config", "-n", "source.py", "other.py")
        self.observe((command,))
        branch = self.branch("irrelevant", **{"source.py": "changed pattern-named file\n"})
        hit = self.memory.check_command(command, branch)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["dependencies"], ["other.py"])

    def test_rg_no_matches_is_not_invented_success(self):
        command = self.command("rg", "--no-config", "absent", "source.py")
        self.observe((command,), results=(CommandResult(command, 1, "", "", 0.01),))
        self.assertEqual(self.memory.check_command(command, self.snapshot())["return_code"], 1)

    def test_rg_config_dependency_unknown_without_no_config(self):
        command = self.command("rg", "value", "source.py")
        with patch.dict(os.environ, {"RIPGREP_CONFIG_PATH": str(self.seed / "config")}):
            self.observe((command,))
            self.assertIsNone(self.memory.check_command(command, self.snapshot()))

    def test_environment_changes_invalidate_read(self):
        command = self.command("cat", "source.py")
        self.observe((command,))
        with patch.dict(os.environ, {"V11_TEST_LOCALE": "different"}):
            self.assertIsNone(self.memory.check_command(command, self.snapshot()))

    def test_large_python_executable_does_not_disable_safe_read_cache(self):
        command = self.command("python", "-c", "from pathlib import Path; print(Path('source.py').read_text())")
        original = EvidenceMemory._file_hash

        def bounded_hash(path, *, max_size=16 * 1024 * 1024):
            if Path(path).resolve() == Path(sys.executable).resolve() and max_size < 128 * 1024 * 1024:
                return None
            return original(path, max_size=max_size)

        with patch.object(EvidenceMemory, "_file_hash", side_effect=bounded_hash):
            self.observe((command,))
            self.assertIsNotNone(self.memory.check_command(command, self.snapshot()))

    def test_truncated_failed_blocked_and_timeout_reads_are_not_cached(self):
        command = self.command("cat", "source.py")
        original = CommandResult(command, 0, "x", "", 0.01)
        for result in (replace(original, output_truncated=True), replace(original, blocked=True),
                       replace(original, timed_out=True), replace(original, return_code=1),
                       replace(original, stderr="warning")):
            self.memory = EvidenceMemory(self.seed)
            self.observe((command,), results=(result,))
            self.assertIsNone(self.memory.check_command(command, self.snapshot()))

    def test_read_after_write_in_same_batch_is_not_cached(self):
        write = self.command("python", "-c", "open('source.py','w').write('transient')")
        read = self.command("cat", "source.py")
        revert = self.command("python", "-c", "open('source.py','w').write('value = 1\\n')")
        self.observe((write, read, revert), results=(CommandResult(write, 0, "", "", .01),
                      CommandResult(read, 0, "transient", "", .01), CommandResult(revert, 0, "", "", .01)))
        self.assertIsNone(self.memory.check_command(read, self.snapshot()))

    def test_read_before_write_is_keyed_to_pre_write_dependencies(self):
        read = self.command("cat", "source.py")
        write = self.command("python", "-c", "write()")
        branch = self.branch("write-after", **{"source.py": "value = 2\n"})
        self.observe((read, write), after=branch)
        self.assertIsNone(self.memory.check_command(read, branch))
        self.assertEqual(self.memory.check_command(read, self.snapshot())["stdout"], "value = 1\n")

    def test_failed_public_verification_survives_unrelated_commands_and_branching(self):
        check = self.command("python", "-m", "pytest", "tests/test_public.py")
        self.observe(verification=(check,))
        self.observe((self.command("cat", "other.py"),))
        branch = self.branch("later", **{"source.py": "value = 2\n"})
        obligation = self.memory.verification_obligations(branch)[0]
        self.assertEqual(obligation["command"], check)
        self.assertEqual(obligation["status"], "stale_failed")
        self.assertTrue(obligation["needs_recheck"])
        self.assertEqual(obligation["dependency_scope"], "whole_workspace")

    def test_pass_clears_only_same_check_current_fingerprint(self):
        check = self.command("python", "-m", "pytest", "tests/test_public.py")
        self.observe(verification=(check,))
        self.observe(verification=(check,), verification_results=(CommandResult(check, 0, "1 passed", "", .01),))
        obligation = self.memory.verification_obligations(self.snapshot())[0]
        self.assertEqual(obligation["status"], "passed")
        self.assertFalse(obligation["needs_recheck"])
        self.assertTrue(obligation["ever_failed"])
        changed = self.branch("changed-after-pass", **{"other.py": "other = 2\n"})
        self.assertEqual(self.memory.verification_obligations(changed)[0]["status"], "stale_passed")

    def test_regular_pytest_command_is_also_public_check(self):
        check = self.command("pytest", "tests/test_public.py")
        self.observe((check,), results=(CommandResult(check, 1, "1 failed", "", .01),))
        self.assertEqual(self.memory.verification_obligations(self.snapshot())[0]["status"], "failed")

    def test_check_before_later_command_has_unknown_dependency_state(self):
        check = self.command("pytest", "tests/test_public.py")
        write = self.command("python", "-c", "write()")
        self.observe((check, write), results=(CommandResult(check, 0, "1 passed", "", .01), CommandResult(write, 0, "", "", .01)))
        self.assertEqual(self.memory.verification_obligations(self.snapshot())[0]["status"], "stale_passed")

    def test_verification_seed_and_snapshot_absolute_alias_deduplicates(self):
        first = self.command("python", "-m", "pytest", str(self.seed / "tests"))
        self.observe(verification=(first,))
        branch = self.branch("test-alias")
        second = self.command("python", "-m", "pytest", str(Path(branch.location) / "tests"))
        self.observe(verification=(second,), after=branch, verification_results=(CommandResult(second, 0, "1 passed", "", .01),))
        self.assertEqual(len(self.memory.verification_obligations(branch)), 1)
        self.assertEqual(self.memory.verification_obligations(branch)[0]["status"], "passed")

    def test_context_compact_error_priority_and_actual_render_metrics(self):
        for i in range(12):
            self.observe((self.command("python", "-c", "print(" + str(i) + ")"),))
        check = self.command("python", "-c", "assert " + "True and " * 400 + "False")
        self.observe(verification=(check,))
        rendered = self.memory.context(self.snapshot(), limit_chars=1200)
        self.assertLessEqual(len(json.dumps(rendered, ensure_ascii=False)), 1200)
        self.assertEqual(rendered["obligations"][0]["return_code"], 1)
        self.assertIn("AssertionError", rendered["obligations"][0]["evidence"])
        self.assertTrue(rendered["obligations"][0]["command_truncated"])
        self.assertEqual(self.memory.metrics["rendered_obligations"], len(rendered["obligations"]))
        self.assertEqual(self.memory.metrics["rendered_observations"], len(rendered["recent_evidence"]))
        self.assertGreater(rendered["omitted_records"], 0)

    def test_tiny_context_limits_respected(self):
        self.observe((self.command("cat", "source.py"),))
        for limit in (2, 10, 40, 200, 400):
            rendered = self.memory.context(self.snapshot(), limit)
            self.assertLessEqual(len(json.dumps(rendered, ensure_ascii=False)), limit)

    def test_observation_storage_is_deduplicated_and_bounded(self):
        self.memory = EvidenceMemory(self.seed, max_records=8)
        for i in range(12):
            self.observe((self.command("python", "-c", str(i)),))
        self.observe((self.command("python", "-c", "11"),))
        self.assertEqual(len(self.memory._records), 8)
        self.assertEqual(self.memory.metrics["evicted_observations"], 4)

    def test_symlink_dependency_never_cached(self):
        link = self.seed / "linked.py"
        try:
            link.symlink_to(self.seed / "source.py")
        except OSError:
            self.skipTest("Symlink privilege unavailable")
        command = self.command("cat", "linked.py")
        self.observe((command,))
        self.assertIsNone(self.memory.check_command(command, self.snapshot()))

    def test_cache_context_marks_it_as_old_observation(self):
        command = self.command("cat", "source.py")
        self.observe((command,))
        self.memory.check_command(command, self.snapshot())
        context = self.memory.context(self.snapshot())
        self.assertEqual(context["cached_reads"][0]["status"], "previously_reused_not_current_validation")

    def test_python_path_read_text_encoding_slice_cache(self):
        source = "from pathlib import Path; print(Path('source.py').read_text(encoding='utf-8', errors='replace')[0:300:1])"
        command = self.command("python", "-c", source)
        self.observe((command,))
        self.assertEqual(self.memory.check_command(command, self.snapshot())["stdout"], "value = 1\n")

    def test_python_path_read_bytes_and_negative_slice_cache(self):
        command = self.command("python3.11", "-c", "import pathlib as p; print(p.Path('source.py').read_bytes()[-20:])")
        self.observe((command,), results=(CommandResult(command, 0, "b'value = 1\\n'\n", "", .01),))
        self.assertEqual(self.memory.check_command(command, self.snapshot())["dependencies"], ["source.py"])

    def test_python_assignments_splitlines_and_join_cache(self):
        source = "from pathlib import Path\np=Path('source.py')\ns=p.read_text().splitlines()\nprint('\\n'.join(s[:30]))"
        command = self.command("python", "-c", source)
        self.observe((command,))
        self.assertIsNotNone(self.memory.check_command(command, self.snapshot()))

    def test_python_stdin_read_cache(self):
        source = "from pathlib import Path\nprint(Path('source.py').read_text())"
        command = self.command("python", "-", stdin=source)
        self.observe((command,))
        self.assertIsNotNone(self.memory.check_command(command, self.snapshot()))

    def test_python_literal_path_aliases_match_across_snapshots(self):
        source = "from pathlib import Path; print(Path(%r).read_text())" % str(self.seed / "source.py")
        command = self.command("python", "-c", source)
        self.observe((command,))
        branch = self.branch("python-alias")
        other_source = "from pathlib import Path; print(Path(%r).read_text())" % str(Path(branch.location) / "source.py")
        self.assertIsNotNone(self.memory.check_command(self.command("python", "-c", other_source), branch))

    def test_python_printed_literal_alias_is_not_normalized(self):
        source = "from pathlib import Path; print(%r, Path('source.py').read_text())" % str(self.seed)
        command = self.command("python", "-c", source)
        self.observe((command,))
        branch = self.branch("literal-path")
        other_source = "from pathlib import Path; print(%r, Path('source.py').read_text())" % branch.location
        self.assertIsNone(self.memory.check_command(self.command("python", "-c", other_source), branch))

    def test_python_path_shadowing_prevents_reuse(self):
        command = self.command("python", "-c", "from pathlib import Path; print(Path('source.py').read_text())")
        self.observe((command,))
        branch = self.branch("shadowed", **{"pathlib.py": "raise RuntimeError('do not execute')"})
        self.assertIsNone(self.memory.check_command(command, branch))

    def test_python_unsafe_or_unknown_ast_never_cache(self):
        scripts = [
            "from pathlib import Path; print(Path('source.py').write_text('bad'))",
            "from pathlib import Path; print(Path(input()).read_text())",
            "from pathlib import Path; print(Path('source.py').read_text()); __import__('os').system('whoami')",
            "from pathlib import Path; exec('print(1)'); print(Path('source.py').read_text())",
            "import os; from pathlib import Path; print(Path('source.py').read_text())",
            "from pathlib import Path; print(Path('source.py').read_text(), file=open('other.py','w'))",
            "from pathlib import Path; x='source.py'; print(Path(x).read_text())",
            "from pathlib import Path; print(Path('source.py').read_text()[int(input()):])",
            "from pathlib import Path; print(Path('source.py').read_text()[::0])",
            "from pathlib import Path; print = Path('source.py'); print.read_text()",
            "from pathlib import Path; print([p.read_text() for p in Path('.').glob('*')])",
            "from pathlib import Path; print(Path('source.py').read_text(encoding=input()))",
            "print('ok')",
        ]
        for source in scripts:
            command = self.command("python", "-c", source)
            self.observe((command,))
            self.assertIsNone(self.memory.check_command(command, self.snapshot()), source)

    def test_compact_failed_observation_keeps_stale_branch_provenance(self):
        command = self.command("tool", "source.py")
        self.observe((command,), results=(CommandResult(command, 1, "", "ValueError: source is invalid", .01),))
        changed = self.branch("new-approach", **{"source.py": "value = 2\n"})
        view = self.memory.context(changed)["recent_evidence"][0]
        self.assertEqual(view["status"], "stale_workspace_observation")
        self.assertEqual(view["source_snapshot"], self.seed.name)
        self.assertIn("source is invalid", view["evidence"])

    def test_failed_intermediate_command_never_claims_final_state(self):
        first = self.command("inspect", "source.py")
        second = self.command("edit", "source.py")
        self.observe((first, second), results=(CommandResult(first, 0, "old source", "", .01),
                                             CommandResult(second, 0, "new source", "", .01)))
        views = self.memory.context(self.snapshot())["recent_evidence"]
        first_view = next(item for item in views if item["argv"][0] == "inspect")
        self.assertEqual(first_view["status"], "unknown_intermediate_state")


if __name__ == "__main__":
    unittest.main()
