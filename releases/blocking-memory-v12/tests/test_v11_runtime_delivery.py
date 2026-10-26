"""End-to-end delivery/validation regressions using deterministic model replies."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.evidence_runtime import run_evidence
from bestfgs.models import TaskSpec
from bestfgs.retrac_adapter import RetracModelConfig
from bestfgs.submission import inspect_git_submission, resolve_git_base


class Replies:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = 0

    def complete_json(self, **kwargs):
        self.calls += 1
        return next(self.replies)

    def usage_summary(self):
        return {"logical_calls": self.calls}


def command(script):
    return {"argv": [sys.executable, "-c", script], "description": "public fixture check"}


def decision(*commands, checks=(), done=False):
    return {"commands": list(commands), "verification_commands": list(checks), "done": done}


class RuntimeDeliveryV11Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "answer.py").write_text("answer = 0\n", encoding="utf-8")
        self.config = RetracModelConfig("offline-fixture", "https://invalid.example", "unused", parse_attempts=1)

    def make_git(self):
        def git(*args):
            subprocess.run(["git", *args], cwd=self.seed, capture_output=True, check=True)
        git("init")
        git("config", "core.autocrlf", "false")
        git("add", ".")
        git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "base")
        return resolve_git_base(self.seed)

    def run_task(self, replies, *, tools=10, memory=False, branching=False):
        environment = ForkedWorkspaceEnvironment(self.seed, self.root / "runs")
        result = run_evidence(TaskSpec.create("Fix answer"), environment, Replies(replies), self.config,
                              max_iterations=10, max_tool_calls=tools, max_commands=6,
                              memory_enabled=memory, branching_enabled=branching)
        return result

    def assert_working_checks_not_passed(self, result):
        self.assertIsNot(result.get("working_snapshot_validation_passed", result["local_validation_passed"]), True)

    def test_partial_verification_budget_is_not_a_full_pass(self):
        result = self.run_task([
            decision(command("from pathlib import Path; Path('answer.py').write_text('answer = 42\\n')"),
                     checks=(command("assert True"), command("assert False, 'second obligation not satisfied'"))),
        ], tools=2)
        self.assertEqual(result["total_tool_calls"], 2)
        self.assert_working_checks_not_passed(result)

    def test_later_narrow_check_does_not_erase_an_unreplayed_failure(self):
        result = self.run_task([
            decision(checks=(command("assert False, 'public regression remains unresolved'"),)),
            decision(checks=(command("assert True"),)),
            decision(done=True),
        ])
        self.assert_working_checks_not_passed(result)

    def test_clean_delivery_cannot_inherit_check_that_relied_on_ignored_source(self):
        (self.seed / ".gitignore").write_text("ignored_fix.py\n", encoding="utf-8")
        self.make_git()
        result = self.run_task([
            decision(command("from pathlib import Path; Path('answer.py').write_text('from ignored_fix import answer\\n'); "
                             "Path('ignored_fix.py').write_text('answer = 42\\n')"),
                     checks=(command("import answer; assert answer.answer == 42"),)),
            decision(done=True),
        ])
        delivered = Path(result["best_workspace"])
        self.assertFalse((delivered / "ignored_fix.py").exists())
        actual = subprocess.run([sys.executable, "-c", "import answer; assert answer.answer == 42"],
                                cwd=delivered, capture_output=True)
        self.assertNotEqual(actual.returncode, 0)
        self.assertIsNot(result["local_validation_passed"], True)

    def test_source_recreated_only_during_verification_is_not_a_pass(self):
        self.make_git()
        result = self.run_task([
            decision(command("from pathlib import Path; Path('answer.py').unlink()"),
                     checks=(command("from pathlib import Path; Path('answer.py').write_text('answer = 42\\n'); "
                                     "import answer; assert answer.answer == 42"),)),
            decision(done=True),
        ])
        self.assert_working_checks_not_passed(result)
        self.assertFalse((Path(result["best_workspace"]) / "answer.py").exists())

    def test_delivery_reexports_exact_source_patch_and_never_claims_official_success(self):
        base = self.make_git()
        result = self.run_task([
            decision(command("from pathlib import Path; Path('answer.py').write_text('answer = 42\\n')"),
                     checks=(command("import answer; assert answer.answer == 42"),)),
            decision(done=True),
        ])
        patch = inspect_git_submission(Path(result["best_workspace"]), base)
        self.assertIn(b"+answer = 42", patch.patch)
        self.assertEqual(result["delivery"]["patch_sha256"], patch.patch_sha256)
        self.assertTrue(result["delivery"]["roundtrip_verified"])
        self.assertFalse(result["succeeded"])
        self.assertFalse(result["verified_success"])
        self.assertIsNone(result["official_resolved"])


if __name__ == "__main__":
    unittest.main()
