from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.evidence_runtime import run_evidence, parse_decision, SYSTEM_PROMPT
from bestfgs.experiment_metrics import ExperimentRecorder
from bestfgs.models import TaskSpec, ModelCallError
from bestfgs.raw_baseline import run_raw
from bestfgs.retrac_adapter import RetracModelConfig
from bestfgs.submission import inspect_git_submission, resolve_git_base


def wire(code):
    return {"argv": [sys.executable, "-c", code], "description": "public test command"}


def turn(code):
    return {"done": False, "commands": [wire(code)]}


def verify(code):
    return {"done": False, "verification_commands": [wire(code)]}


class Client:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.prompts = []

    def complete_json(self, **kwargs):
        self.prompts.append(kwargs)
        value = next(self.payloads)
        if callable(value):
            value = value(json.loads(kwargs["user_prompt"]))
        if isinstance(value, Exception):
            raise value
        return value

    def usage_summary(self):
        return {"model_calls": len(self.prompts), "api_requests": len(self.prompts)}


class EvidenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "answer.py").write_text("answer = 1\n", encoding="utf-8")
        self.config = RetracModelConfig(api_key="fake", model_name="test-only", base_url="https://example.invalid",
                                        max_commands_per_action=4, parse_attempts=2)
        self.seq = 0

    def run_agent(self, payloads, *, memory=True, branching=True, iterations=12, tools=20, git=False):
        if git and not (self.seed / ".git").exists():
            if not shutil.which("git"):
                self.skipTest("Git required")
            for args in (["init", "-q"], ["add", "."],
                         ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "seed"]):
                subprocess.run(["git", *args], cwd=self.seed, capture_output=True, check=True)
        self.seq += 1
        directory = self.root / f"run-{self.seq}"
        recorder = ExperimentRecorder(directory / "cli-metrics.jsonl")
        environment = ForkedWorkspaceEnvironment(self.seed, directory, recorder=recorder)
        client = Client(payloads)
        result = run_evidence(TaskSpec.create("Make answer equal two"), environment, client,
                              self.config, max_iterations=iterations, max_tool_calls=tools,
                              max_commands=4, memory_enabled=memory, branching_enabled=branching)
        return result, client, directory

    def test_sequential_fix_verify_submit_without_assessment_calls(self):
        result, client, root = self.run_agent([
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"),
            verify("from answer import answer; assert answer == 2"),
            {"done": True}], git=True)
        self.assertEqual(result["stop_reason"], "submitted")
        self.assertEqual(result["decision_turns"], 3)
        self.assertEqual(result["interaction_rounds"], 2)
        self.assertEqual(result["total_tool_calls"], 2)
        self.assertEqual(result["model_usage"]["model_calls"], 3)
        self.assertTrue(result["submitted"])
        self.assertTrue(result["working_snapshot_validation_passed"])
        self.assertFalse(result["local_validation_passed"])
        self.assertFalse(result["succeeded"])
        self.assertIsNone(result["official_resolved"])
        self.assertTrue(result["delivery"]["roundtrip_verified"])
        self.assertEqual((Path(result["best_workspace"]) / "answer.py").read_text(), "answer = 2\n")
        self.assertEqual((self.seed / "answer.py").read_text(), "answer = 1\n")
        self.assertEqual(json.loads((root / "search_checkpoint.json").read_text())["delivery"], result["delivery"])
        self.assertEqual(len(json.loads(client.prompts[2]["user_prompt"])["transcript"]), 4)

    def test_raw_and_evidence_share_prompt_tools_delivery_and_fixed_budget(self):
        payload = [turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"),
                   verify("from answer import answer; assert answer == 2"), {"done": True}]
        raw, rawclient, _ = self.run_agent(payload, memory=False, branching=False, git=True)
        agent, agentclient, _ = self.run_agent(payload, git=True)
        for field in ("decision_turns", "interaction_rounds", "total_tool_calls", "budget", "local_validation_passed"):
            self.assertEqual(raw[field], agent[field], field)
        self.assertEqual(raw["delivery"]["patch_sha256"], agent["delivery"]["patch_sha256"])
        self.assertEqual(rawclient.prompts[0]["system_prompt"], SYSTEM_PROMPT)
        self.assertTrue(agentclient.prompts[0]["system_prompt"].startswith(SYSTEM_PROMPT))
        self.assertNotIn("task_evidence", json.loads(rawclient.prompts[1]["user_prompt"]))
        self.assertNotIn("available_snapshots", json.loads(rawclient.prompts[1]["user_prompt"]))
        self.assertEqual(raw["search_algorithm"], "raw_cli")

    def test_schema_repair_is_not_a_tool_round_or_unbounded_new_decision(self):
        result, _, _ = self.run_agent([{"done": "bad"}, {"done": True}], memory=False, branching=False)
        self.assertEqual(result["decision_turns"], 1)
        self.assertEqual(result["model_usage"]["model_calls"], 2)
        self.assertEqual(result["interaction_rounds"], 0)

    def test_combined_batch_limit_and_submit_no_hidden_commands(self):
        with self.assertRaises(ValueError):
            parse_decision({"done": False, "commands": [wire("print(1)")] * 3,
                            "verification_commands": [wire("print(1)")] * 2}, self.config)
        with self.assertRaises(ValueError):
            parse_decision({"done": True, "commands": [wire("print(1)")]}, self.config)

    def test_tool_budget_counts_verification_and_no_extra_request(self):
        result, client, _ = self.run_agent([{"done": False, "commands": [wire("print(1)")],
                                           "verification_commands": [wire("print(2)")]}], tools=2)
        self.assertEqual(result["stop_reason"], "tool_budget")
        self.assertEqual(result["total_tool_calls"], 2)
        self.assertEqual(len(client.prompts), 1)
        self.assertEqual(result["comparison_metrics"]["tool_calls"], 2)

    def test_restore_branches_files_but_keeps_transcript_and_consumes_decision(self):
        def restore_root(prompt):
            return {"done": False, "restore_snapshot": prompt["available_snapshots"][0]["id"],
                    "branch_reason": "That edit was unsuitable"}
        result, client, _ = self.run_agent([
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 99\\n')"),
            restore_root,
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"),
            {"done": True}], git=True)
        self.assertEqual(result["snapshot_restores"], 1)
        self.assertEqual(result["decision_turns"], 4)
        self.assertEqual(result["interaction_rounds"], 2)
        self.assertIn("Restored task files", json.loads(client.prompts[2]["user_prompt"])["transcript"][-1]["content"])
        self.assertEqual((Path(result["best_workspace"]) / "answer.py").read_text(), "answer = 2\n")

    def test_no_automatic_restore_or_extra_retries_on_model_outage(self):
        result, _, root = self.run_agent([
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"),
            ModelCallError("test outage")], git=True)
        self.assertEqual(result["stop_reason"], "model_unavailable")
        self.assertEqual(result["total_tool_calls"], 1)
        self.assertEqual(result["snapshot_restores"], 0)
        self.assertEqual(result["delivery"]["status"], "draft")
        self.assertTrue((root / "search_checkpoint.json").exists())

    def test_latest_narrow_pass_does_not_erase_previous_failed_check(self):
        result, _, _ = self.run_agent([
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"),
            verify("from answer import answer; assert answer == 3"),
            verify("from answer import answer; assert answer > 0"), {"done": True}], git=True)
        self.assertTrue(result["submitted"])
        self.assertFalse(result["local_validation_passed"])
        self.assertEqual(result["unresolved_or_stale_check_count"], 1)

    def test_changed_source_invalidates_check_even_if_later_other_test_passes(self):
        result, _, _ = self.run_agent([
            verify("from answer import answer; assert answer == 1"),
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"),
            verify("from answer import answer; assert answer > 0"), {"done": True}])
        self.assertFalse(result["local_validation_passed"])
        self.assertEqual(result["unresolved_or_stale_check_count"], 1)

    def test_explicit_empty_submit_not_silently_replaced_by_old_patch(self):
        def restore_root(prompt):
            return {"done": False, "restore_snapshot": prompt["available_snapshots"][0]["id"],
                    "branch_reason": "Return to initial files"}
        result, _, _ = self.run_agent([
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"),
            restore_root, {"done": True}], git=True)
        self.assertEqual(result["stop_reason"], "empty_submission")
        self.assertFalse(result["delivery"]["has_patch"])
        self.assertFalse(result["submitted"])
        self.assertTrue(result["model_task_success_claimed"])

    def test_budget_after_restore_preserves_last_nonempty_draft_with_provenance(self):
        def restore_root(prompt):
            return {"done": False, "restore_snapshot": prompt["available_snapshots"][0]["id"],
                    "branch_reason": "Try another approach"}
        result, _, _ = self.run_agent([
            turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"), restore_root],
            git=True, iterations=2)
        self.assertEqual(result["candidate_selection"], "last_nonempty_draft")
        self.assertFalse(result["submitted"])
        self.assertTrue(result["delivery"]["has_patch"])
        self.assertNotEqual(result["selected_snapshot_id"], result["current_snapshot_id"])

    @unittest.skipUnless(shutil.which("cat"), "cat needed for portable exact-read integration")
    def test_cached_read_is_not_a_tool_execution_and_decisions_stay_bounded(self):
        read = {"done": False, "commands": [{"argv": ["cat", "answer.py"], "description": "read"}]}
        result, client, root = self.run_agent([read, read, read], iterations=3)
        self.assertEqual(result["total_tool_calls"], 1)
        self.assertEqual(result["cached_tool_observations"], 2)
        self.assertEqual(result["decision_turns"], 3)
        self.assertEqual(result["comparison_metrics"]["tool_calls"], 1)
        self.assertIn("CACHED OBSERVATIONS", json.loads(client.prompts[2]["user_prompt"])["transcript"][-1]["content"])
        trace = json.loads((root / "evidence-trace.json").read_text())
        self.assertEqual(sum(x["cached_observations"] for x in trace["decisions"]), 2)

    def test_unknown_command_not_reused_by_description(self):
        result, _, _ = self.run_agent([turn("print('same')"), turn("print('same')"), {"done": True}])
        self.assertEqual(result["total_tool_calls"], 2)
        self.assertEqual(result["cached_tool_observations"], 0)

    def test_python_path_reads_reused_in_real_environment_on_windows_and_linux(self):
        read = turn("from pathlib import Path; print(Path('answer.py').read_text(encoding='utf-8'))")
        result, client, _ = self.run_agent([read, read, {"done": True}])
        self.assertEqual(result["total_tool_calls"], 1)
        self.assertEqual(result["cached_tool_observations"], 1)
        self.assertEqual(result["decision_turns"], 3)
        self.assertEqual(result["comparison_metrics"]["tool_calls"], 1)
        self.assertIn("CACHED OBSERVATIONS", json.loads(client.prompts[2]["user_prompt"])["transcript"][-1]["content"])

    def test_read_after_edit_in_same_batch_not_replaced_by_old_cache(self):
        read = wire("from pathlib import Path; print(Path('answer.py').read_text(encoding='utf-8'))")
        write = wire("from pathlib import Path; Path('answer.py').write_text('answer = 22\\n')")
        result, client, _ = self.run_agent([
            {"done": False, "commands": [read]},
            {"done": False, "commands": [read, write, read]}, {"done": True}])
        self.assertEqual(result["cached_tool_observations"], 1)
        self.assertEqual(result["total_tool_calls"], 3)
        feedback = json.loads(client.prompts[2]["user_prompt"])["transcript"][-1]["content"]
        self.assertIn("answer = 22", feedback)

    def test_cached_nonzero_stops_batch_like_real_nonzero(self):
        cached = {"evidence_id": "earlier-rg-no-match", "return_code": 1,
                  "stdout": "", "stderr": "", "cached": True, "source_snapshot": "earlier"}
        with patch("bestfgs.evidence_memory.EvidenceMemory.check_command", return_value=cached):
            result, client, _ = self.run_agent([
                {"done": False, "commands": [wire("print('first')"),
                 wire("from pathlib import Path; Path('answer.py').write_text('wrong')")],
                 "verification_commands": [wire("print('should not run')")]}, {"done": True}])
        self.assertEqual(result["total_tool_calls"], 0)
        self.assertEqual(result["cached_tool_observations"], 1)
        self.assertEqual((Path(result["best_workspace"]) / "answer.py").read_text(), "answer = 1\n")
        self.assertEqual(result["unresolved_or_stale_check_count"], 1)
        self.assertIn("rest of BOTH command lists was NOT executed", json.loads(client.prompts[1]["user_prompt"])["transcript"][-1]["content"])

    def test_schema_failure_is_not_labelled_infrastructure_outage(self):
        result, _, _ = self.run_agent([{"done": "bad"}, {"done": "bad"}])
        self.assertEqual(result["stop_reason"], "model_output_invalid")
        self.assertEqual(result["failure_kind"], "model_output")
        self.assertEqual(result["model_usage"]["model_calls"], 2)

    def test_verification_only_is_in_loop_and_counted_not_free_final_validation(self):
        result, _, _ = self.run_agent([verify("from answer import answer; assert answer == 1"), {"done": True}])
        self.assertEqual(result["comparison_metrics"]["tool_calls_by_phase"], {"functional_verification": 1})
        self.assertEqual(result["interaction_rounds"], 1)
        self.assertEqual(result["comparison_metrics"]["interaction_rounds"], 1)

    def test_syntax_failure_not_erased_by_unrelated_passing_verification(self):
        result, _, _ = self.run_agent([
            turn("from pathlib import Path; Path('answer.py').write_text('this is invalid python syntax :')"),
            verify("print('unrelated pass')"), {"done": True}])
        self.assertFalse(result["local_validation_passed"])

    def test_explicit_evidence_cli_and_notebook_export_use_v12_engine_without_legacy_judge(self):
        from bestfgs import __main__ as cli
        import run_notebook
        if not shutil.which("git"):
            self.skipTest("Git required")
        for args in (["init", "-q"], ["add", "."],
                     ["-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "seed"]):
            subprocess.run(["git", *args], cwd=self.seed, capture_output=True, check=True)
        base = resolve_git_base(self.seed)
        attempt = self.root / "attempt"
        client = Client([turn("from pathlib import Path; Path('answer.py').write_text('answer = 2\\n')"), {"done": True}])
        output = io.StringIO()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only"}), \
             patch("bestfgs.retrac_adapter.OpenAICompatibleJSONClient", return_value=client), \
             patch.object(cli, "TaskRunner", side_effect=AssertionError("Legacy runtime must not run")), \
             patch("bestfgs.success_judge.IndependentSuccessJudge", side_effect=AssertionError("No judge")), \
             redirect_stdout(output):
            code = cli.main(["--engine", "evidence", "--goal", "Make answer equal two", "--workspace", str(self.seed),
                             "--run-root", str(attempt / "snapshots"), "--provider", "deepseek",
                             "--model", "test-only", "--quiet", "--comparison-metrics"])
        result = json.loads(output.getvalue())
        self.assertEqual(result["runtime_version"], "blocking-cli-v12")
        self.assertEqual(code, 1)
        details, patch_text = run_notebook.validate_result_artifact(result, code=code, attempt=attempt,
                                                                  benchmark="swebench", task={"base_commit": base})
        self.assertIn("+answer = 2", patch_text)
        self.assertTrue(details["submitted"])
        self.assertFalse(details["agent_succeeded"])
        self.assertEqual(details["patch_sha256"], result["delivery"]["patch_sha256"])


if __name__ == "__main__":
    unittest.main()
