import json
from dataclasses import replace
from types import SimpleNamespace
import unittest

from terminal_context import BudgetExceeded, Limits, MemoryCandidate, TaskContext, TerminalEvent
from terminal_context.adapters import from_command_result
from terminal_context.compression import command_type, compress


def event(command="python app.py", **kwargs):
    return replace(TerminalEvent("T1", command, cwd="/repo", workspace="W1",
                                 environment="V1", exit_code=0), **kwargs)


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.context = TaskContext("T1", "Fix the application", constraints=("Do not delete data",))

    def remember(self, context=None, **kwargs):
        c = context or self.context
        return c.remember(MemoryCandidate(**({
            "conclusion": "python app.py requires the project environment",
            "applies_when": "python app.py", "evidence_ids": ("E1",),
        } | kwargs)))

    def test_ordinary_success_is_not_memory_or_task_success(self):
        result = self.context.observe(event(stdout="ok"))
        self.assertEqual(result["outcome"], "exit_zero")
        self.assertEqual(self.context.snapshot()["memories"], [])
        self.assertIn("not task success", result["note"])

    def test_repeated_failure_admitted_without_causal_claim(self):
        failure = event(stderr="ModuleNotFoundError: No module named 'flask'", exit_code=1)
        self.context.observe(failure)
        self.assertEqual(self.context.snapshot()["memories"], [])
        self.context.observe(failure)
        memory = self.context.recall()[0]
        self.assertEqual(memory["kind"], "failure")
        self.assertEqual(len(memory["evidence"]), 2)
        self.assertIn("not a prohibition", memory["applies_when"])
        self.context.observe(failure)
        self.assertEqual(len(self.context.snapshot()["memories"]), 1)
        self.assertEqual(len(self.context.snapshot()["memories"][0]["evidence"]), 3)

    def test_recovery_after_environment_change_is_not_causality(self):
        self.context.observe(event(stderr="ImportError: missing dependency", exit_code=1))
        self.context.observe(event(environment="V2", stdout="ok"))
        memory = self.context.recall()[0]
        self.assertEqual(memory["kind"], "recovery")
        self.assertIn("not established", memory["conclusion"])
        self.assertEqual(self.context.snapshot()["state"], {})

    def test_unknown_scope_disables_automatic_memory(self):
        failure = event(workspace=None, environment=None, stderr="ValueError: bad", exit_code=1)
        self.context.observe(failure)
        self.context.observe(failure)
        self.assertEqual(self.context.recall(), [])

    def test_low_value_rejected_and_foreign_evidence_rejected(self):
        self.context.observe(event())
        self.assertIsNone(self.remember(value=1))
        with self.assertRaises(ValueError):
            self.remember(evidence_ids=("E999",))
        with self.assertRaises(ValueError):
            self.context.observe(event(task_id="T2"))

    def test_scope_invalidation_and_narrow_dependency(self):
        self.context.observe(event())
        self.remember(dependencies=("environment",))
        self.context.set_scope(cwd="/repo", workspace="W2", environment="V1")
        self.assertEqual(len(self.context.recall("python")), 1)
        self.context.set_scope(cwd="/repo", workspace="W2", environment="V2")
        self.assertEqual(self.context.recall("python"), [])
        self.assertEqual(self.context.snapshot()["memories"][0]["validity"], "stale")

    def test_unknown_revision_does_not_revalidate_memory(self):
        self.context.observe(event())
        self.remember()
        self.context.set_scope(cwd="/repo")
        self.assertEqual(self.context.recall("python"), [])
        self.assertEqual(self.context.snapshot()["memories"][0]["validity"], "unknown")
        with self.assertRaises(ValueError):
            self.remember()

    def test_cwd_change_invalidates_even_environment_only_rule(self):
        self.context.observe(event())
        self.remember(dependencies=("environment",))
        self.context.set_scope(cwd="/other", workspace="W1", environment="V1")
        self.assertEqual(self.context.recall("python"), [])

    def test_no_match_is_not_failure(self):
        result = self.context.observe(event("rg missing .", exit_code=1))
        self.assertEqual(result["outcome"], "no_match")

    def test_ttl_eviction(self):
        c = TaskContext("T1", "test", limits=Limits(memory_ttl_steps=2))
        c.observe(event())
        self.remember(c)
        for _ in range(3):
            c.observe(event("ls"))
        self.assertEqual(c.snapshot()["memories"], [])

    def test_latest_survives_tiny_history_budget(self):
        c = TaskContext("T1", "test", limits=Limits(recent_bytes=2))
        c.observe(event(stderr="ValueError: broken", exit_code=1))
        c.observe(event(stderr="ValueError: broken", exit_code=1))
        snap = c.snapshot()
        self.assertEqual(snap["recent"], [])
        self.assertEqual(snap["latest_feedback"]["id"], "E2")
        self.assertEqual(len(snap["memories"]), 1)
        self.assertEqual(json.loads(c.build_prompt().content)["latest_feedback"]["id"], "E2")

    def test_storage_stays_bounded_in_long_task(self):
        limits = Limits(recent_count=3, recent_bytes=5000, memory_count=3,
                        memory_bytes=4000, state_count=3, state_bytes=3000)
        c = TaskContext("T1", "test", limits=limits)
        for i in range(120):
            result = c.observe(event(f"python app{i}.py", stdout="noise\n" * 1000,
                                     stderr="ValueError: failure", exit_code=1))
            self.assertLessEqual(len(result["output"]), limits.feedback_chars)
            self.remember(c, conclusion=f"app{i} failure", applies_when=f"app{i}",
                          evidence_ids=(result["id"],))
            snap = c.snapshot()
            for part, count, cap in (("recent", 3, 5000), ("memories", 3, 4000), ("state", 3, 3000)):
                self.assertLessEqual(len(snap[part]), count)
                name = "memory" if part == "memories" else part
                self.assertLessEqual(snap["stats"][name + "_bytes"], cap)

    def test_prompt_budget_and_mandatory_content(self):
        for i in range(5):
            self.context.observe(event(f"cat file{i}", stdout="data\n" * 400))
        view = self.context.build_prompt(max_units=6000, reserved_units=1000)
        self.assertLessEqual(view.units, 5000)
        self.assertEqual(view.units, len(view.content.encode("utf-8")))
        payload = json.loads(view.content)
        self.assertEqual(payload["goal"], "Fix the application")
        self.assertEqual(payload["constraints"], ["Do not delete data"])
        self.assertEqual(payload["latest_feedback"]["id"], "E5")
        with self.assertRaises(BudgetExceeded):
            self.context.build_prompt(max_units=100)

    def test_custom_counter_and_rebuild_not_append(self):
        self.context.observe(event())
        first = self.context.build_prompt(counter=len, unit_name="characters")
        second = self.context.build_prompt(counter=len, unit_name="characters")
        self.assertEqual(first, second)
        self.assertEqual(first.units, len(first.content))
        with self.assertRaises(ValueError):
            self.context.build_prompt(counter=lambda _: -1)

    def test_explicit_memory_recalled_into_prompt(self):
        self.context.observe(event())
        mid = self.remember()
        view = self.context.build_prompt()
        self.assertIn(mid, view.selected_memory_ids)
        self.assertEqual(json.loads(view.content)["task_memory"][0]["strength"], "hypothesis")

    def test_memory_evidence_survives_history_eviction_but_raw_does_not(self):
        c = TaskContext("T1", "test", limits=Limits(recent_count=1))
        c.observe(event(stdout="hello"))
        self.remember(c)
        c.observe(event("ls"))
        self.assertIsNotNone(c.read_evidence("E1"))
        self.assertLessEqual(len(c.read_evidence("E1")["quote"]), 400)
        self.assertIsNone(c.read_evidence("E999"))

    def test_copies_cannot_mutate_storage(self):
        record = self.context.observe(event())
        self.remember()
        record["scope"]["workspace"] = "hack"
        memories = self.context.recall()
        memories[0]["evidence"][0]["quote"] = "hack"
        self.assertNotEqual(self.context.read_evidence("E1")["quote"], "hack")
        self.assertEqual(self.context.snapshot()["scope"]["workspace"], "W1")

    def test_stdin_identity_prevents_false_repetition(self):
        self.context.observe(event("python", input_digest="input1", stderr="ValueError: bad", exit_code=1))
        self.context.observe(event("python", input_digest="input2", stderr="ValueError: bad", exit_code=1))
        self.assertEqual(self.context.snapshot()["memories"], [])

    def test_invalid_limits(self):
        for kwargs in ({"memory_bytes": 1}, {"recent_count": 0}, {"feedback_chars": 100}):
            with self.assertRaises(ValueError):
                Limits(**kwargs)

    def test_adapter_does_not_expose_stdin(self):
        result = SimpleNamespace(command=SimpleNamespace(argv=("python", "file name.py"), stdin="private-input"),
                                 stdout="ok", stderr="", return_code=0)
        converted = from_command_result("T1", result, cwd="/repo", workspace="W1", environment="V1")
        self.assertEqual(converted.command, "python 'file name.py'")
        self.assertEqual(len(converted.input_digest), 64)
        self.assertNotIn("private-input", str(converted))


class CompressionTests(unittest.TestCase):
    def check(self, e):
        return compress(e, max_chars=500, scan_chars=2000)

    def test_command_types(self):
        for command, expected in (("pytest tests/a.py", "pytest"), ("python3 -m pytest", "pytest"),
                                  ("cat 'a b.py'", "read"), ("pytest | tail", "generic"),
                                  ("bash -c 'pytest'", "generic"), ("git diff", "git"),
                                  ("npm test", "test"), ("pip install flask", "install")):
            self.assertEqual(command_type(command), expected, command)

    def test_pytest_scope_and_no_tests(self):
        passed = self.check(event("pytest tests/a.py", stdout="=== 2 passed, 1 skipped in 0.12s ==="))
        self.assertEqual(passed.test_status, "passed_scope_only")
        empty = self.check(event("pytest", stdout="no tests ran in 0.02s", exit_code=5))
        self.assertEqual(empty.test_status, "no_tests")

    def test_incomplete_timeout_unknown_or_missing_summary_never_pass(self):
        base = event("pytest", stdout="1 passed in 0.01s")
        for e in (replace(base, output_truncated=True), replace(base, timed_out=True),
                  replace(base, blocked=True), replace(base, exit_code=None),
                  replace(base, stdout="I predict 1 passed in 0.01s"),
                  replace(base, stdout="x" * 3000 + "\n1 passed in 0.01s")):
            self.assertEqual(self.check(e).test_status, "unverified")

    def test_nonzero_exit_overrides_passed_footer(self):
        result = self.check(event("pytest", stdout="1 passed in 0.01s", exit_code=1))
        self.assertEqual(result.test_status, "failed")

    def test_failed_footer_prevents_pass_with_zero_exit(self):
        result = self.check(event("pytest", stdout="1 passed, 1 failed in 0.01s"))
        self.assertNotEqual(result.test_status, "passed_scope_only")

    def test_large_multilingual_output_stays_bounded_and_marked(self):
        result = self.check(event("cat source.py", stdout="中文内容\n" * 10000))
        self.assertLessEqual(len(result.output), 500)
        self.assertTrue(result.incomplete)
        self.assertTrue(result.reduced)
        self.assertIn("clipped", result.output)


if __name__ == "__main__":
    unittest.main()
