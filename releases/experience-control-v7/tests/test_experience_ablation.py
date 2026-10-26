"""No model/network calls: contract tests for bounded, fixed-denominator ablation."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_experience_ablation as ablation
from benchmark_runtime import atomic_write_json


class ExperienceAblationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "source.py").write_text("x = 1\n", encoding="utf-8")
        # Fingerprint-only fake executable; every execution uses a scripted fixture.
        self.python = self.root / "env/bin/python"
        self.python.parent.mkdir(parents=True)
        self.python.write_bytes(b"never execute this fixture")
        self.metadata = self.root / "env/lib/python3.11/site-packages/example.dist-info/METADATA"
        self.metadata.parent.mkdir(parents=True)
        self.metadata.write_text("Name: example\nVersion: 1\n", encoding="utf-8")
        self.manifest = self.root / "tasks.json"
        self.output = self.root / "new-ablation"
        self.data = {"schema_version": 1, "benchmark": "custom", "tasks": [
            {"id": "dev-01", "goal": "Fix public behavior", "workspace": "seed", "task_python": "env/bin/python"},
            {"id": "dev-02", "goal": "Fix other public behavior", "workspace": "seed", "task_python": "env/bin/python"}]}
        self.write_manifest()
        self.env = patch.dict(os.environ, {"DEEPSEEK_API_KEY": "private-test-secret", "DEEPSEEK_MODEL": "fixture-model"})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Source edits by parallel agents must not make this unit fixture flaky.
        identity = patch.object(ablation, "implementation_identity", return_value={"fixture": "stable-implementation"})
        identity.start()
        self.addCleanup(identity.stop)

    def write_manifest(self):
        atomic_write_json(self.manifest, self.data)

    def argv(self, *extra):
        return ["--task-manifest", str(self.manifest), "--output-root", str(self.output),
                "--python", str(self.python), "--model", "fixture-model", *extra]

    def plan(self, *extra):
        return ablation.build_plan(ablation.parser().parse_args(self.argv(*extra)))

    def fixture_executor(self, job, plan, environment):
        self.assertEqual(environment["DEEPSEEK_API_KEY"], "private-test-secret")
        self.assertNotIn("private-test-secret", json.dumps(job))
        self.assertEqual(job["extra"][-2:], ["--experience-mode", job["mode"]])
        output = Path(job["output_root"])
        attempt = output / job["id"] / "attempt-fixture"
        attempt.mkdir(parents=True)
        metrics = {"metric_version": ablation.METRIC_VERSION, "trace_complete": True,
                   "interaction_rounds": 2, "tool_calls": 5, "redundant_tool_calls": 1}
        result = {"succeeded": False, "submitted": True, "local_validation_passed": True,
                  "official_resolved": True,  # Untrusted internal assertion must not become an official outcome.
                  "delivery": {"status": "submitted", "has_patch": True}, "comparison_metrics": metrics,
                  "model_usage": {"model_calls": 4, "api_requests": 5, "api_responses": 4,
                                  "prompt_tokens": 100, "completion_tokens": 20},
                  "experience_report": {"mode": job["mode"], "runtime_events": {"gated_candidates": 99},
                                        "false_block_rate": None, "causal_tool_calls_saved": None}}
        result_path = attempt / "agent-result.json"
        atomic_write_json(result_path, result)
        atomic_write_json(output / job["id"] / "status.json", {"status": "completed", "attempt": str(attempt),
                          "result_sha256": ablation.file_hash(result_path)})
        return 0

    def execute(self, executor=None):
        plan = self.plan("--execute")
        result = ablation.execute_plan(plan, executor=executor or self.fixture_executor)
        return plan, result

    def test_default_plan_makes_no_calls_or_files_and_contains_no_key(self):
        output = io.StringIO()
        with patch.object(ablation, "execute_plan", side_effect=AssertionError("No execution by default")), redirect_stdout(output):
            self.assertEqual(ablation.main(self.argv()), 0)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["execution_requested"])
        self.assertEqual(len(payload["commands"]), 6)
        self.assertNotIn("private-test-secret", output.getvalue())
        self.assertFalse(self.output.exists())

    def test_plan_reproducible_order_and_only_arm_flag_differs(self):
        one, two = self.plan(), self.plan()
        self.assertEqual(one["protocol_sha256"], two["protocol_sha256"])
        jobs = list(ablation.jobs(one))
        self.assertEqual([j["id"] for j in jobs], ["dev-01"] * 3 + ["dev-02"] * 3)
        self.assertEqual({tuple(j["extra"][:-2]) for j in jobs}, {tuple(one["protocol"]["common_agent_args"])})
        self.assertEqual({j["extra"][-1] for j in jobs}, set(ablation.MODES))
        self.assertEqual(len({j["output_root"] for j in jobs}), 6)
        self.assertTrue(one["protocol"]["ordinary_history_retained_in_all_arms"])
        self.assertEqual(one["protocol"]["attempts_per_task_arm"], 1)
        self.assertNotIn("--resume", json.dumps(jobs))
        for mode in ablation.MODES:
            self.assertEqual([j["id"] for j in jobs if j["mode"] == mode], ["dev-01", "dev-02"])

    def test_schedule_seed_does_not_increase_budget_or_repeat_tasks(self):
        a, b = self.plan("--schedule-seed", "1"), self.plan("--schedule-seed", "2")
        self.assertNotEqual(a["protocol_sha256"], b["protocol_sha256"])
        self.assertEqual(a["protocol"]["common_agent_args"], b["protocol"]["common_agent_args"])
        self.assertEqual(a["protocol"]["expected_ids"], b["protocol"]["expected_ids"])
        self.assertEqual(len(list(ablation.jobs(a))), len(list(ablation.jobs(b))))

    def test_large_batch_rejected_before_workspace_reads(self):
        self.data["tasks"] = [{"id": str(i), "workspace": "missing"} for i in range(100)]
        self.write_manifest()
        with patch.object(ablation.notebook, "load_tasks", side_effect=AssertionError("Do not walk 100 seeds")), self.assertRaisesRegex(ValueError, "1-10"):
            self.plan()

    def test_actual_notebook_schema_only_and_runtime_must_be_explicit(self):
        atomic_write_json(self.manifest, {"tasks": self.data["tasks"]})
        with self.assertRaisesRegex(ValueError, "schema_version"):
            self.plan()
        self.data["tasks"][0].pop("task_python")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "EVERY task"):
            self.plan()
        plan = self.plan("--task-python", str(self.python))
        self.assertEqual({t["task_python"] for t in plan["protocol"]["tasks"]}, {str(self.python)})

    def test_duplicate_and_frozen_ids_use_existing_notebook_validation(self):
        self.data["tasks"][1]["id"] = "dev-01"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.plan()
        self.data["tasks"][1]["id"] = "dev-02"
        self.data["benchmark"] = "terminal-bench"
        self.write_manifest()
        with patch.object(ablation.notebook, "reject_frozen_overlap", side_effect=RuntimeError("frozen overlap")) as check:
            with self.assertRaisesRegex(RuntimeError, "frozen overlap"):
                self.plan()
            self.assertEqual(set(check.call_args.args[0]), {"dev-01", "dev-02"})
            self.assertEqual(check.call_args.kwargs, {"benchmark": "terminal-bench", "allow_frozen_test_set": False})

    def test_output_root_never_reused_even_when_empty(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.plan()

    def test_sensitive_endpoint_rejected(self):
        for endpoint in ("https://user:password@api.example", "https://api.example?key=secret", "http://api.example"):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError, "HTTPS"):
                self.plan("--base-url", endpoint)

    def test_execute_requires_gate_and_key_without_output(self):
        with self.assertRaisesRegex(ValueError, "--execute"):
            ablation.execute_plan(self.plan(), executor=self.fixture_executor)
        plan = self.plan("--execute")
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), self.assertRaisesRegex(ValueError, "not set"):
            ablation.execute_plan(plan, executor=self.fixture_executor)
        self.assertFalse(self.output.exists())

    def test_seed_and_dependency_drift_stop_before_paid_execution(self):
        plan = self.plan("--execute")
        self.metadata.write_text("Version: 2\n")
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            ablation.execute_plan(plan, executor=lambda *a: self.fail("must not execute"))
        self.assertFalse(self.output.exists())
        plan = self.plan("--execute")
        (self.seed / "source.py").write_text("x = 2\n")
        with self.assertRaisesRegex(ValueError, "seed changed"):
            ablation.execute_plan(plan, executor=lambda *a: self.fail("must not execute"))

    def test_midrun_drift_aborts_remaining_arms_and_keeps_record(self):
        calls = []
        def drift(job, plan, env):
            calls.append(job)
            code = self.fixture_executor(job, plan, env)
            self.metadata.write_text("Version: drift\n")
            return code
        with self.assertRaisesRegex(ValueError, "metadata changed"):
            self.execute(drift)
        self.assertEqual(len(calls), 1)
        report = ablation.summarize(self.output)
        self.assertEqual(sum(a["statuses"].get("completed", 0) for a in report["arms"].values()), 1)
        self.assertEqual(sum(a["planned_N"] for a in report["arms"].values()), 6)

    def test_complete_run_uses_original_metrics_and_never_claims_official_success(self):
        plan, code = self.execute()
        self.assertEqual(code, 0)
        report = ablation.summarize(self.output)
        for arm in report["arms"].values():
            self.assertEqual(arm["planned_N"], 2)
            self.assertEqual(arm["mean_interaction_rounds"], 2)
            self.assertEqual(arm["tool_calls"], 10)
            self.assertEqual(arm["redundant_tool_calls"], 2)
            self.assertEqual(arm["tool_call_redundancy_rate_micro"], .2)
            self.assertEqual(arm["recorded_model_usage"]["prompt_tokens"]["recorded_total"], 200)
            self.assertEqual(arm["official_unknown"], 2)
            self.assertIsNone(arm["official_resolved"])
            self.assertIsNone(arm["official_success_rate"])
            self.assertIsNone(arm["monetary_cost"])
            self.assertIsNone(arm["false_block_rate"])
            self.assertIsNone(arm["causal_tool_calls_saved"])
        with self.assertRaises(FileExistsError):
            ablation.execute_plan(plan, executor=lambda *a: self.fail("no rerun"))

    def test_failed_runs_still_in_metrics_denominator_and_never_retried(self):
        calls = []
        def failed(job, plan, env):
            calls.append((job["id"], job["mode"]))
            code = self.fixture_executor(job, plan, env)
            if job["mode"] == "conditioned" and job["id"] == "dev-01":
                path = Path(job["output_root"]) / job["id"] / "status.json"
                state = ablation.read_optional(path)
                state["status"] = "error"
                atomic_write_json(path, state)
                return 2
            return code
        _, code = self.execute(failed)
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), len(set(calls)))
        arm = ablation.summarize(self.output)["arms"]["conditioned"]
        self.assertEqual(arm["planned_N"], 2)
        self.assertEqual(arm["statuses"]["error"], 1)
        self.assertEqual(arm["mean_interaction_rounds"], 2)

    def test_missing_metrics_not_zero_or_excluded_and_cost_remains_recorded(self):
        self.execute()
        job = next(j for j in ablation.jobs(ablation.read_optional(self.output / "ablation-plan.json")) if j["mode"] == "off")
        state = ablation.read_optional(Path(job["output_root"]) / job["id"] / "status.json")
        path = Path(state["attempt"]) / "agent-result.json"
        result = ablation.read_optional(path)
        result["comparison_metrics"]["trace_complete"] = False
        atomic_write_json(path, result)
        state["result_sha256"] = ablation.file_hash(path)
        atomic_write_json(Path(job["output_root"]) / job["id"] / "status.json", state)
        report = ablation.summarize(self.output)
        arm = report["arms"]["off"]
        self.assertEqual(arm["planned_N"], 2)
        self.assertEqual(arm["complete_metric_tasks"], 1)
        self.assertIsNone(arm["mean_interaction_rounds"])
        self.assertIsNone(arm["tool_call_redundancy_rate_micro"])
        self.assertEqual(arm["recorded_model_usage"]["prompt_tokens"]["recorded_total"], 200)

    def test_tampered_protocol_and_result_do_not_silently_mix(self):
        self.execute()
        plan = ablation.read_optional(self.output / "ablation-plan.json")
        job = next(ablation.jobs(plan))
        state = ablation.read_optional(Path(job["output_root"]) / job["id"] / "status.json")
        (Path(state["attempt"]) / "agent-result.json").write_text("{}")
        report = ablation.summarize(self.output)
        row = next(r for r in report["tasks"][job["mode"]] if r["id"] == job["id"])
        self.assertEqual(row["status"], "artifact_error")
        self.assertIsNone(row["comparison_metrics"])
        plan["protocol"]["common_agent_args"].append("--unsafe")
        atomic_write_json(self.output / "ablation-plan.json", plan)
        with self.assertRaisesRegex(ValueError, "invalid protocol"):
            ablation.summarize(self.output)

    def test_summary_only_never_executes_and_works_without_credentials(self):
        self.execute()
        output = io.StringIO()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}), patch.object(ablation, "execute_plan", side_effect=AssertionError("read only")), redirect_stdout(output):
            self.assertEqual(ablation.main(["--summarize", "--output-root", str(self.output)]), 0)
        self.assertFalse(json.loads(output.getvalue())["official_evaluation"])

    def test_reviewed_plan_hash_mismatch_is_rejected_without_execution(self):
        with patch.object(ablation, "execute_plan", side_effect=AssertionError("must not launch")), redirect_stderr(io.StringIO()):
            self.assertEqual(ablation.main(self.argv("--execute", "--expected-protocol-sha256", "wrong-hash")), 2)
        self.assertFalse(self.output.exists())

    def test_trace_is_original_recorder_source_and_mismatch_is_audited(self):
        self.execute()
        plan = ablation.read_optional(self.output / "ablation-plan.json")
        job = next(ablation.jobs(plan))
        state = ablation.read_optional(Path(job["output_root"]) / job["id"] / "status.json")
        # This is the same attempt/snapshots/cli-metrics.jsonl location produced
        # by run_notebook --run-root and __main__.ExperimentRecorder.
        path = Path(state["attempt"]) / "snapshots/cli-metrics.jsonl"
        path.parent.mkdir()
        events = [{"event": "header", "metric_version": ablation.METRIC_VERSION},
                  {"event": "round_start", "round_id": 1, "phase": "action"},
                  {"event": "tool_start", "call_id": 1, "phase": "action"},
                  {"event": "tool_end", "call_id": 1, "redundant": False, "blocked": False,
                   "timed_out": False, "instrumentation_seconds": 0}]
        path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        report = ablation.summarize(self.output)
        row = next(row for row in report["tasks"][job["mode"]] if row["id"] == job["id"])
        self.assertEqual(row["comparison_metrics"], ablation.summarize_trace(path))
        self.assertEqual(row["comparison_metrics"]["tool_calls"], 1)
        self.assertIn("result/trace metric mismatch", row["audit_errors"][0])

    def test_damaged_execution_record_stays_in_denominator(self):
        self.execute()
        (self.output / "execution/off/dev-01.json").write_text("broken JSON", encoding="utf-8")
        report = ablation.summarize(self.output)
        self.assertEqual(report["arms"]["off"]["planned_N"], 2)
        self.assertEqual(report["arms"]["off"]["statuses"]["artifact_error"], 1)
        # Independent result accounting is still available despite damaged status.
        self.assertEqual(report["arms"]["off"]["mean_interaction_rounds"], 2)

    def test_missing_status_retains_unique_partial_result_without_retry(self):
        self.execute()
        plan = ablation.read_optional(self.output / "ablation-plan.json")
        job = next(ablation.jobs(plan))
        (Path(job["output_root"]) / job["id"] / "status.json").unlink()
        report = ablation.summarize(self.output)
        row = next(row for row in report["tasks"][job["mode"]] if row["id"] == job["id"])
        self.assertEqual(row["status"], "partial_artifacts")
        self.assertEqual(row["comparison_metrics"]["tool_calls"], 5)
        self.assertIsNone(row["official_resolved"])


if __name__ == "__main__":
    unittest.main()
