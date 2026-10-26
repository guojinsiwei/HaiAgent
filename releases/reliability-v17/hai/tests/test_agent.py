from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from haiagent.demo import ScriptedClient, demo
from haiagent.executor import LocalExecutor, Result, workspace_revision
from haiagent.metrics import attach_evaluation, prepare_audit, summarize_manifest, summarize_run
from haiagent.model import APIClient, ModelError, request_with_deadline
from haiagent.protocol import Config, Task, parse_decision
from haiagent.runtime import run
from haiagent.storage import Recorder, atomic_json, read_trace
from haiagent.submission import inspect_git_submission, resolve_git_base


class FakeExecutor:
    def __init__(self, result=None):
        self.commands = []
        self.result = result or Result(0, stdout="known fact")

    def execute(self, command, deadline):
        self.commands.append(command)
        return self.result


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hai-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.task = Task("T1", "inspect the files", self.workspace, delivery="terminal")
        self.config = Config(max_turns=5, max_tools=4, wall_seconds=10)
        self.out = self.root / "run"

    def execute(self, actions, *, config=None, task=None, executor=None):
        client = ScriptedClient(actions)
        result = run(task or self.task, config or self.config, client, self.out, executor=executor or FakeExecutor())
        return result, client

    def test_model_may_submit_immediately_without_forced_tools_or_judge(self):
        executor = FakeExecutor()
        result, _ = self.execute([{"action": "submit", "summary": "No action needed"}], executor=executor)
        self.assertTrue(result["submitted"])
        self.assertIsNone(result["success"])
        self.assertEqual(result["interaction_rounds"], 1)
        self.assertEqual(result["tool_calls"], 0)
        self.assertEqual(executor.commands, [])

    def test_run_then_submit_counts_all_decisions(self):
        result, _ = self.execute([{"action": "run", "argv": ["ls"]}, {"action": "submit", "summary": "done"}])
        metrics = summarize_run(self.out)
        self.assertEqual(result["interaction_rounds"], 2)
        self.assertEqual(metrics["tool_feedback_rounds"], 1)
        self.assertIsNone(metrics["tool_redundancy_rate"])
        self.assertEqual(metrics["unknown_calls"], 1)
        self.assertNotIn("mechanical_repeat_rate", metrics)

    def test_raw_has_no_context_or_memory_protocol(self):
        _, client = self.execute([{"action": "run", "argv": ["ls"]}, {"action": "submit", "summary": "done"}],
                                 config=replace(self.config, method="raw"))
        initial = json.loads(client.requests[0][1]["content"])
        self.assertNotIn("context", initial)
        self.assertNotIn('"memory" object', client.requests[0][0]["content"])

    def test_hai_rebuilds_exactly_one_context_block_per_request(self):
        _, client = self.execute([{"action": "run", "argv": ["ls"]}, {"action": "submit", "summary": "done"}])
        self.assertIn("context", json.loads(client.requests[1][1]["content"]))
        self.assertEqual(sum('"current_scope"' in m["content"] for m in client.requests[1]), 1)

    def test_optional_memory_affects_following_request(self):
        result, client = self.execute([
            {"action": "run", "argv": ["cat", "config.py"]},
            {"action": "run", "argv": ["cat", "config.py"],
             "memory": {"conclusion": "config.py contains the setting", "applies_when": "inspect config.py files",
                        "evidence_ids": ["E1"], "kind": "finding", "dependencies": ["workspace"]}},
            {"action": "submit", "summary": "done"},
        ])
        payload = json.loads(client.requests[2][1]["content"])
        self.assertEqual(len(payload["context"]["task_memory"]), 1)
        self.assertTrue(result["submitted"])

    def test_format_error_consumes_a_turn_and_executes_nothing(self):
        executor = FakeExecutor()
        result, _ = self.execute([{"action": "run", "argv": "bad"}, {"action": "submit", "summary": "done"}], executor=executor)
        self.assertEqual(result["interaction_rounds"], 2)
        self.assertEqual(executor.commands, [])
        self.assertEqual(summarize_run(self.out)["format_errors"], 1)

    def test_truncated_response_is_not_executed(self):
        class TruncatedClient:
            def complete(self, *args):
                return {"content": '{"action":"run","argv":["ls"]}', "complete": False}
        executor = FakeExecutor()
        result = run(self.task, replace(self.config, max_turns=1), TruncatedClient(), self.out, executor=executor)
        self.assertEqual(executor.commands, [])
        self.assertEqual(result["stop_reason"], "turn_budget")
        self.assertFalse(result["submitted"])

    def test_tool_budget_still_allows_model_submission(self):
        result, _ = self.execute([{"action": "run", "argv": ["ls"]}, {"action": "submit", "summary": "done"}],
                                 config=replace(self.config, max_tools=1))
        self.assertTrue(result["submitted"])

    def test_tool_budget_never_executes_extra_command(self):
        executor = FakeExecutor()
        result, _ = self.execute([{"action": "run", "argv": ["ls"]}] * 2,
                                 config=replace(self.config, max_tools=1), executor=executor)
        self.assertEqual(len(executor.commands), 1)
        self.assertEqual(result["stop_reason"], "tool_budget")

    def test_no_overwrite_or_inside_workspace_log(self):
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            self.execute([])
        with self.assertRaises(ValueError):
            run(self.task, self.config, ScriptedClient([]), self.workspace / "logs")

    def test_trace_tampering_rejected(self):
        self.execute([{"action": "submit", "summary": "done"}])
        trace = self.out / "events.jsonl"
        trace.write_text(trace.read_text(encoding="utf-8").replace('"summary":"done"', '"summary":"fake"'), encoding="utf-8")
        with self.assertRaises(ValueError):
            summarize_run(self.out)

    def test_semantic_audit_can_label_different_commands_redundant(self):
        self.execute([{"action": "run", "argv": ["cat", "a.py"]},
                      {"action": "run", "argv": ["sed", "-n", "1,100p", "a.py"]},
                      {"action": "submit", "summary": "done"}])
        path = self.root / "audit.json"
        audit = prepare_audit(self.out, path)
        self.assertNotIn("method", audit)
        audit["reviewer"] = "human-r1"
        audit["calls"][0].update(label="nonredundant", reason="First view of the relevant file")
        audit["calls"][1].update(label="redundant", reason="The entire short file was visible, unchanged, and no new verification obligation existed",
                                 category="equivalent_information", conditions_unchanged=True, evidence_call_ids=[1])
        atomic_json(path, audit)
        summary = summarize_run(self.out, path)
        self.assertEqual(summary["tool_redundancy_rate"], 0.5)
        self.assertEqual(summary["audit_coverage"], 1)
        audit["calls"][1]["evidence_call_ids"] = [3]
        atomic_json(path, audit)
        with self.assertRaises(ValueError):
            summarize_run(self.out, path)

    def test_same_command_can_be_nonredundant(self):
        self.execute([{"action": "run", "argv": ["pytest"]}] * 2 + [{"action": "submit", "summary": "done"}])
        path = self.root / "audit.json"
        audit = prepare_audit(self.out, path)
        audit["reviewer"] = "human-r1"
        for row in audit["calls"]:
            row.update(label="nonredundant", reason="Independent repetition needed to investigate suspected flakiness")
        atomic_json(path, audit)
        self.assertEqual(summarize_run(self.out, path)["tool_redundancy_rate"], 0)

    def test_unknowns_not_silently_nonredundant(self):
        self.execute([{"action": "run", "argv": ["ls"]}, {"action": "submit", "summary": "done"}])
        summary = summarize_run(self.out)
        self.assertIsNone(summary["tool_redundancy_rate"])
        self.assertEqual(summary["redundancy_lower_bound"], 0)
        self.assertEqual(summary["redundancy_upper_bound"], 1)

    def test_evaluation_requires_actual_source_and_artifact_binding(self):
        result, _ = self.execute([{"action": "submit", "summary": "done"}])
        source = self.root / "official.json"
        source.write_text('{"task_id":"T1","reward":0}', encoding="utf-8")
        report = {"schema": "hai-external-evaluation-v1", "run_id": result["run_id"], "task_id": "T1",
                  "artifact_sha256": result["artifact"]["sha256"], "success": False, "independent": True,
                  "evaluator": "independent-fixture-evaluator", "source_report": "official.json", "source_format": "fixture-reward-v1",
                  "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        report_path = self.root / "normalized.json"
        atomic_json(report_path, report)
        attach_evaluation(self.out, report_path)
        self.assertIs(summarize_run(self.out)["success"], False)
        with self.assertRaises(ValueError):
            attach_evaluation(self.out, report_path)
        source.write_text('{"reward":1}', encoding="utf-8")
        self.assertIs(summarize_run(self.out)["success"], False)  # immutable portable copy
        (self.out / "evaluation-source.json").write_text('{"reward":1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            summarize_run(self.out)

    def test_manifest_keeps_missing_and_unevaluated_tasks(self):
        self.execute([{"action": "submit", "summary": "done"}])
        manifest = self.root / "manifest.json"
        atomic_json(manifest, {"task_ids": ["T1", "T2"], "methods": {"hai": {"T1": {"run": "run"}}}})
        report = summarize_manifest(manifest)["methods"]["hai"]
        self.assertEqual(report["missing_task_ids"], ["T2"])
        self.assertIsNone(report["success_rate"])
        self.assertIsNone(report["average_interaction_rounds"])
        self.assertEqual(report["completed_run_average_rounds"], 1)

    def test_git_delivery_includes_new_and_staged_files_without_changing_index(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.workspace, capture_output=True, check=True).stdout
        git("init", "-q")
        (self.workspace / "a.py").write_text("a=1\n")
        git("add", ".")
        git("-c", "user.name=Test", "-c", "user.email=test@invalid", "commit", "-qm", "base")
        base = resolve_git_base(self.workspace)
        (self.workspace / "a.py").write_text("a=2\n")
        git("add", ".")
        (self.workspace / "a.py").write_text("a=3\n")
        (self.workspace / "new.py").write_text("n=1\n")
        index_before = (self.workspace / ".git/index").read_bytes()
        patch = inspect_git_submission(self.workspace, base)
        self.assertIn(b"+a=3", patch.patch)
        self.assertIn("new.py", patch.changed_paths)
        self.assertEqual(index_before, (self.workspace / ".git/index").read_bytes())

    def test_empty_git_submission_rejected_without_forced_tests(self):
        subprocess.run(["git", "init", "-q"], cwd=self.workspace, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@invalid", "commit", "--allow-empty", "-qm", "base"], cwd=self.workspace, check=True)
        result, _ = self.execute([{"action": "submit", "summary": "done"}],
                                 task=replace(self.task, delivery="git_patch"), config=replace(self.config, max_turns=1))
        self.assertFalse(result["submitted"])
        self.assertEqual(result["tool_calls"], 0)

    def test_real_offline_demo(self):
        result = demo(self.out)
        self.assertTrue(result["demo_check_passed"])
        self.assertTrue(result["submitted"])
        self.assertEqual(result["tool_calls"], 3)
        self.assertIsNone(result["success"])

    def test_executor_captures_large_output_and_stdin(self):
        executor = LocalExecutor(self.task, replace(self.config, output_bytes=512))
        command = parse_decision({"action": "run", "argv": [sys.executable, "-c", "import sys; print(sys.stdin.read()); print('x'*10000)"], "stdin": "hello"})
        result = executor.execute(command, time.monotonic() + 5)
        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.output_truncated)
        self.assertLess(len(result.stdout), 600)
        self.assertIn("hello", result.stdout)

    def test_executor_wall_limit(self):
        executor = LocalExecutor(self.task, self.config)
        command = parse_decision({"action": "run", "argv": [sys.executable, "-c", "import time; time.sleep(20)"], "timeout_seconds": 20})
        start = time.monotonic()
        result = executor.execute(command, start + 0.15)
        self.assertTrue(result.timed_out)
        self.assertLess(time.monotonic() - start, 5)

    def test_executor_blocks_escaping_cwd(self):
        result = LocalExecutor(self.task, self.config).execute(parse_decision({"action": "run", "argv": ["no-command"], "cwd": ".."}), time.monotonic() + 1)
        self.assertTrue(result.blocked)

    def test_revision_changes_and_incomplete_scan_is_unknown(self):
        (self.workspace / "a").write_text("one")
        first = workspace_revision(self.workspace)
        (self.workspace / "a").write_text("two")
        self.assertNotEqual(first, workspace_revision(self.workspace))
        self.assertIsNone(workspace_revision(self.workspace, max_bytes=1))

    def test_recorder_redacts_actual_key(self):
        recorder = Recorder(self.out, secrets=("secret-test-key",))
        recorder.emit("header", detail="secret-test-key")
        self.assertNotIn("secret-test-key", recorder.path.read_text())
        self.assertEqual(read_trace(recorder.path)[0]["detail"], "[REDACTED]")

    def test_audit_contains_only_model_visible_prior_excerpt_for_visibility_check(self):
        huge = "a" * 5000 + "HIDDEN_MIDDLE_FACT" + "b" * 5000
        self.execute([{"action": "run", "argv": ["cat", "a.py"]},
                      {"action": "run", "argv": ["cat", "a.py"]},
                      {"action": "submit", "summary": "done"}],
                     executor=FakeExecutor(Result(0, stdout=huge)))
        audit = prepare_audit(self.out, self.root / "audit.json")
        shown = json.dumps(audit["calls"][1]["information_available_before_call"])
        self.assertNotIn("HIDDEN_MIDDLE_FACT", shown)
        self.assertIn("HIDDEN_MIDDLE_FACT", audit["calls"][0]["result"]["stdout"])

    def test_control_credentials_not_in_command_environment(self):
        command = parse_decision({"action": "run", "argv": [sys.executable, "-c", "import os; print(os.getenv('HAI_API_KEY')); print(os.getenv('OTHER_PRIVATE_KEY'))"]})
        with patch.dict("os.environ", {"HAI_API_KEY": "sensitive-fixture", "OTHER_PRIVATE_KEY": "another-fixture"}):
            result = LocalExecutor(self.task, self.config).execute(command, time.monotonic() + 5)
        self.assertEqual(result.stdout.strip().splitlines(), ["None", "None"])

    def test_response_after_deadline_never_executes_command(self):
        class SlowClient:
            def complete(self, *args):
                time.sleep(0.12)
                return {"complete": True, "content": '{"action":"run","argv":["ls"]}'}
        executor = FakeExecutor()
        result = run(self.task, replace(self.config, wall_seconds=0.1), SlowClient(), self.out, executor=executor)
        self.assertEqual(result["stop_reason"], "wall_budget")
        self.assertEqual(executor.commands, [])

    def test_comparison_refuses_mismatched_budgets(self):
        self.execute([{"action": "submit", "summary": "done"}])
        run(self.task, replace(self.config, method="raw", max_turns=7),
            ScriptedClient([{"action": "submit", "summary": "done"}]), self.root / "raw")
        manifest = self.root / "manifest.json"
        atomic_json(manifest, {"task_ids": ["T1"], "methods": {
            "hai": {"T1": {"run": "run"}}, "raw": {"T1": {"run": "raw"}}}})
        with self.assertRaises(ValueError):
            summarize_manifest(manifest)

    def test_comparison_rounds_match_without_claiming_unevaluated_success(self):
        self.execute([{"action": "submit", "summary": "done"}])
        run(self.task, replace(self.config, method="raw"),
            ScriptedClient([{"action": "submit", "summary": "done"}]), self.root / "raw")
        manifest = self.root / "manifest.json"
        atomic_json(manifest, {"task_ids": ["T1"], "methods": {
            "hai": {"T1": {"run": "run"}}, "raw": {"T1": {"run": "raw"}}}})
        report = summarize_manifest(manifest)
        self.assertTrue(report["common_model_and_budget_match"])
        self.assertEqual(report["paired_comparison"]["rounds_relative_reduction"], 0)
        self.assertIsNone(report["paired_comparison"]["success_relative_improvement"])

    def test_irrelevant_call_can_use_task_evidence_without_prior_tools(self):
        self.execute([{"action": "run", "argv": ["echo", "unrelated"]}, {"action": "submit", "summary": "done"}])
        path = self.root / "audit.json"
        audit = prepare_audit(self.out, path)
        audit["reviewer"] = "human-r1"
        audit["calls"][0].update(label="redundant", category="irrelevant_to_goal", reason="Printing this constant did not inspect files or diagnose tool availability",
                                 task_evidence="inspect the files", conditions_unchanged=True)
        atomic_json(path, audit)
        self.assertEqual(summarize_run(self.out, path)["tool_redundancy_rate"], 1)

    def test_protocol_rejects_submit_commands_and_nonfinite_timeout(self):
        for payload in ({"action": "submit", "summary": "done", "argv": ["ls"]},
                        {"action": "run", "argv": ["ls"], "timeout_seconds": float("nan")}):
            with self.assertRaises(ValueError):
                parse_decision(payload)


class ModelTests(unittest.TestCase):
    def recorder(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        recorder = Recorder(Path(temp.name) / "run")
        recorder.emit("header")
        return recorder

    def test_401_is_terminal_no_retry(self):
        calls = []
        def transport(*args):
            calls.append(args)
            return "http", 401
        client = APIClient("https://example.invalid/v1", "test", "test-key", Config(), transport)
        with self.assertRaises(ModelError):
            client.complete([], time.monotonic() + 3, self.recorder())
        self.assertEqual(len(calls), 1)

    def test_response_usage_counted_without_extra_model_judge(self):
        body = json.dumps({"model": "returned", "choices": [{"message": {"content": '{"action":"submit","summary":"done"}'}, "finish_reason": "stop"}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
        client = APIClient("https://example.invalid/v1", "test", "test-key", Config(response_protocol='json'), lambda *args: ("ok", body))
        recorder = self.recorder()
        response = client.complete([], time.monotonic() + 3, recorder)
        self.assertTrue(response["complete"])
        rows = read_trace(recorder.path)
        self.assertEqual(rows[-1]["usage"]["prompt_tokens"], 10)

    def test_actual_transport_timeout_is_bounded_without_external_api(self):
        # Tiny absolute deadline kills the child before any useful network work.
        start = time.monotonic()
        kind, _ = request_with_deadline("https://127.0.0.1:1", {}, "test-not-secret", 0.001)
        self.assertEqual(kind, "error")
        self.assertLess(time.monotonic() - start, 3)

    def test_provider_retry_is_counted_and_bounded(self):
        replies = iter([("http", 503), ("ok", json.dumps({"choices": [{"message": {"content": '{}'}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 2}}).encode())])
        client = APIClient("https://example.invalid/v1", "test", "test-key", Config(response_protocol='json'), lambda *args: next(replies))
        recorder = self.recorder()
        self.assertTrue(client.complete([], time.monotonic() + 5, recorder)["complete"])
        rows = read_trace(recorder.path)
        self.assertEqual(sum(r["event"] == "api_start" for r in rows), 2)

    def test_example_model_placeholder_refused_before_request(self):
        with self.assertRaises(ValueError):
            APIClient("https://example.invalid/v1", "REPLACE_WITH_MODEL", "test-key", Config())


if __name__ == "__main__":
    unittest.main()
