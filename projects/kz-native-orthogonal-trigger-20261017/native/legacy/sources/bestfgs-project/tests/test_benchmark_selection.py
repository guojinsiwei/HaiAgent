import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from benchmark_metrics import print_research_metrics, summarize_research_metrics
from benchmark_selection import development_selection
from benchmark_splits import FROZEN_MANIFEST, frozen_swebench_ids, frozen_terminal_task_names
import run_swebench
import run_swebench_18tasks
import run_swebench_2random_tasks
import run_swebench_tenth
import run_terminal_bench_2random_tasks
import run_terminal_bench_tenth


class DevelopmentSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "selection.json"
        self.population = [f"dev-{i}" for i in range(80)] + ["held-out"]

    def select(self, **overrides):
        options = dict(
            path=self.path, benchmark="test", dataset="test/v1",
            protected={"held-out"}, discover=lambda: self.population,
            seed=7, fraction=0.1,
        )
        options.update(overrides)
        return development_selection(**options)

    def test_development_tenth_excludes_held_out_and_freezes_eight(self):
        result = self.select()
        self.assertEqual(result["sample_size"], 8)
        self.assertEqual(result["development_pool_size"], 80)
        self.assertNotIn("held-out", result["task_ids"])
        self.assertEqual(result, json.loads(self.path.read_text(encoding="utf-8")))
        self.assertEqual(result["frozen_manifest_sha256"], hashlib.sha256(FROZEN_MANIFEST.read_bytes()).hexdigest())

    def test_replay_skips_discovery_preserves_order_and_does_not_write(self):
        first = self.select()
        original = self.path.read_bytes()
        discover = Mock(side_effect=AssertionError("must not discover on replay"))
        second = self.select(seed=None, discover=discover)
        self.assertEqual(first, second)
        self.assertEqual(original, self.path.read_bytes())
        discover.assert_not_called()

    def test_seed_reproduces_sample_independent_of_discovery_order(self):
        first = self.select()
        second = self.select(path=self.root / "second.json", discover=lambda: list(reversed(self.population)))
        self.assertEqual(first, second)

    def test_conflicting_seed_does_not_overwrite_selection(self):
        self.select()
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "seed"):
            self.select(seed=8)
        self.assertEqual(original, self.path.read_bytes())

    def test_tampering_is_rejected(self):
        result = self.select()
        result["task_ids"][0] = "edited-task"
        self.path.write_text(json.dumps(result), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "校验失败"):
            self.select()

    def test_wrong_dataset_or_rule_is_rejected(self):
        self.select()
        for overrides in ({"dataset": "different"}, {"fraction": None, "sample_size": 18}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.select(**overrides)

    def test_missing_held_out_tasks_aborts_without_saving(self):
        with self.assertRaisesRegex(ValueError, "缺少冻结"):
            self.select(discover=lambda: ["dev"])
        self.assertFalse(self.path.exists())

    def test_changed_frozen_manifest_rejects_old_selection(self):
        self.select()
        changed = self.root / "changed.json"
        changed.write_text("{}", encoding="utf-8")
        with patch("benchmark_selection.FROZEN_MANIFEST", changed), self.assertRaises(ValueError):
            self.select()

    def test_small_pool_does_not_silently_reduce_eighteen(self):
        with self.assertRaisesRegex(ValueError, "无法抽取18"):
            self.select(fraction=None, sample_size=18, discover=lambda: ["held-out", "dev"])
        self.assertFalse(self.path.exists())

    def test_fraction_rounds_up(self):
        result = self.select(discover=lambda: self.population + ["extra"])
        self.assertEqual(result["sample_size"], 9)

    def test_invalid_population_or_sampling_rule_is_rejected(self):
        for overrides in (
            {"discover": lambda: []},
            {"discover": lambda: ["held-out", "dev", "dev"]},
            {"fraction": 0}, {"fraction": float("nan")},
            {"sample_size": 18}, {"fraction": None},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.select(**overrides)


class BenchmarkEntryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.swe_population = list(frozen_swebench_ids()) + [f"project__issue-{i}" for i in range(450)]
        self.tb_population = list(frozen_terminal_task_names()) + [f"terminal-bench/dev-{i}" for i in range(80)]

    def test_swe18_dry_run_saves_then_replays_without_api_or_docker(self):
        args = ["--sample-seed", "20260904", "--results-dir", str(self.root), "--dry-run"]
        with patch("run_swebench._load_all_instance_ids", return_value=self.swe_population) as discover, patch("run_swebench._run_one_instance") as run, patch("run_swebench._load_public_tasks") as public, patch("builtins.print"):
            self.assertEqual(run_swebench_18tasks.main(args), 0)
            self.assertEqual(run_swebench_18tasks.main(args), 0)
            discover.assert_called_once()
            run.assert_not_called()
            public.assert_not_called()
        saved = json.loads((self.root / "dev18-selection.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["task_ids"]), 18)
        self.assertTrue(set(saved["task_ids"]).isdisjoint(frozen_swebench_ids()))
        self.assertEqual(saved["dataset_size"], 500)

    def test_terminal_tenth_dry_run_saves_eight_and_replays(self):
        selection_path = self.root / "tb.json"
        args = ["--sample-seed", "20260904", "--selection-file", str(selection_path), "--dry-run"]
        with patch("run_terminal_bench_tenth._load_all_task_names", return_value=self.tb_population) as discover, patch("run_terminal_bench._prepare_images") as docker, patch("run_terminal_bench._run_streaming") as run, patch("builtins.print"):
            self.assertEqual(run_terminal_bench_tenth.main(args), 0)
            self.assertEqual(run_terminal_bench_tenth.main(args), 0)
            discover.assert_called_once()
            docker.assert_not_called()
            run.assert_not_called()
        saved = json.loads(selection_path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["task_ids"]), 8)
        self.assertTrue(set(saved["task_ids"]).isdisjoint(frozen_terminal_task_names()))

    def test_terminal_two_task_entry_freezes_two_development_tasks(self):
        selection_path = self.root / "tb-two.json"
        args = [
            "--sample-seed", "20260908",
            "--selection-file", str(selection_path),
            "--dry-run",
        ]
        with patch(
            "run_terminal_bench_2random_tasks._load_all_task_names",
            return_value=self.tb_population,
        ) as discover, patch(
            "run_terminal_bench._prepare_images"
        ) as docker, patch("run_terminal_bench._run_streaming") as run, patch(
            "builtins.print"
        ):
            self.assertEqual(run_terminal_bench_2random_tasks.main(args), 0)
            self.assertEqual(run_terminal_bench_2random_tasks.main(args), 0)
            discover.assert_called_once()
            docker.assert_not_called()
            run.assert_not_called()
        saved = json.loads(selection_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["sample_size"], 2)
        self.assertIsNone(saved["sample_fraction"])
        self.assertTrue(
            set(saved["task_ids"]).isdisjoint(frozen_terminal_task_names())
        )

    def test_swe_tenth_entry_freezes_one_tenth_of_development_pool(self):
        args = [
            "--sample-seed", "20260908",
            "--results-dir", str(self.root),
            "--dry-run",
        ]
        with patch(
            "run_swebench._load_all_instance_ids",
            return_value=self.swe_population,
        ) as discover, patch("run_swebench._run_one_instance") as run, patch(
            "run_swebench._load_public_tasks"
        ) as public, patch("builtins.print"):
            self.assertEqual(run_swebench_tenth.main(args), 0)
            self.assertEqual(run_swebench_tenth.main(args), 0)
            discover.assert_called_once()
            run.assert_not_called()
            public.assert_not_called()
        saved = json.loads(
            (self.root / "dev-tenth-selection.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["sample_size"], 45)
        self.assertEqual(saved["sample_fraction"], 0.1)
        self.assertTrue(set(saved["task_ids"]).isdisjoint(frozen_swebench_ids()))

    def test_swe_two_task_entry_freezes_two_development_tasks(self):
        separate_results = self.root / "swe-two"
        args = [
            "--sample-seed", "20260908",
            "--results-dir", str(separate_results),
            "--dry-run",
        ]
        with patch(
            "run_swebench._load_all_instance_ids",
            return_value=self.swe_population,
        ) as discover, patch("run_swebench._run_one_instance") as run, patch(
            "run_swebench._load_public_tasks"
        ) as public, patch("builtins.print"):
            self.assertEqual(run_swebench_2random_tasks.main(args), 0)
            self.assertEqual(run_swebench_2random_tasks.main(args), 0)
            discover.assert_called_once()
            run.assert_not_called()
            public.assert_not_called()
        saved = json.loads(
            (separate_results / "dev-2-selection.json").read_text(encoding="utf-8")
        )
        self.assertEqual(saved["sample_size"], 2)
        self.assertIsNone(saved["sample_fraction"])
        self.assertTrue(set(saved["task_ids"]).isdisjoint(frozen_swebench_ids()))

    def test_four_development_entries_keep_unified_budget_defaults(self):
        terminal_tenth = run_terminal_bench_tenth.build_parser().parse_args([])
        terminal_two = run_terminal_bench_2random_tasks.build_parser().parse_args([])
        self.assertEqual(
            (terminal_tenth.max_iterations, terminal_tenth.max_tool_calls),
            (24, 80),
        )
        self.assertEqual(
            (terminal_two.max_iterations, terminal_two.max_tool_calls),
            (24, 80),
        )
        self.assertEqual(terminal_tenth.budget_multiplier, 1.0)
        self.assertEqual(terminal_two.budget_multiplier, 1.0)

        for entry, prefix, size, fraction in (
            (run_swebench_tenth, "best-fgs-swe-tenth-", None, 0.1),
            (run_swebench_2random_tasks, "best-fgs-swe-2-", 2, 0.1),
        ):
            with self.subTest(entry=entry.__name__), patch.object(
                entry.run_swebench,
                "main",
                return_value=0,
            ) as run:
                self.assertEqual(entry.main(["--dry-run"]), 0)
            parsed = run_swebench.build_parser().parse_args(run.call_args.args[0])
            self.assertTrue(parsed.run_id.startswith(prefix))
            self.assertEqual((parsed.max_iterations, parsed.max_tool_calls), (24, 80))
            self.assertEqual(parsed.budget_multiplier, 1.0)
            self.assertEqual(parsed.sample_size, size)
            self.assertEqual(parsed.sample_fraction, fraction)

    def test_random_task_entries_accept_configurable_sample_size(self):
        terminal_selection = self.root / "tb-three.json"
        terminal_args = [
            "--sample-size", "3",
            "--sample-seed", "20260908",
            "--selection-file", str(terminal_selection),
            "--dry-run",
        ]
        with patch(
            "run_terminal_bench_2random_tasks._load_all_task_names",
            return_value=self.tb_population,
        ), patch("builtins.print"):
            self.assertEqual(
                run_terminal_bench_2random_tasks.main(terminal_args),
                0,
            )
        terminal_saved = json.loads(
            terminal_selection.read_text(encoding="utf-8")
        )
        self.assertEqual(terminal_saved["sample_size"], 3)

        swe_results = self.root / "swe-three"
        swe_args = [
            "--sample-size", "3",
            "--sample-seed", "20260908",
            "--results-dir", str(swe_results),
            "--dry-run",
        ]
        with patch(
            "run_swebench._load_all_instance_ids",
            return_value=self.swe_population,
        ), patch("builtins.print"):
            self.assertEqual(run_swebench_2random_tasks.main(swe_args), 0)
        swe_saved = json.loads(
            (swe_results / "dev-3-selection.json").read_text(encoding="utf-8")
        )
        self.assertEqual(swe_saved["sample_size"], 3)

    def test_swe_agent_stage_really_runs_two_instances_concurrently(self):
        barrier = threading.Barrier(2)
        state_lock = threading.Lock()
        active = 0
        maximum_active = 0

        def fake_run(_args, **kwargs):
            nonlocal active, maximum_active
            instance_id = kwargs["instance_id"]
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            barrier.wait(timeout=3)
            with state_lock:
                active -= 1
            return (
                {
                    "instance_id": instance_id,
                    "model_name_or_path": "test",
                    "model_patch": "diff",
                },
                {
                    "instance_id": instance_id,
                    "agent_succeeded": True,
                    "agent_stop_reason": "verified_success",
                    "agent_interaction_rounds": 2,
                    "execution_status": "completed",
                },
            )

        args = [
            "--results-dir", str(self.root / "parallel"),
            "--sample-size", "2", "--sample-seed", "17",
            "--run-id", "parallel-test", "--max-workers", "2",
            "--success-judge-mode", "off", "--skip-preflight",
            "--skip-evaluation",
        ]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-only"}), patch(
            "run_swebench._load_all_instance_ids", return_value=self.swe_population
        ), patch(
            "run_swebench._load_public_tasks",
            return_value={item: "fix" for item in self.swe_population},
        ), patch("run_swebench._run_one_instance", side_effect=fake_run) as run, patch(
            "builtins.print"
        ):
            self.assertEqual(run_swebench.main(args), 0)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(maximum_active, 2)

    def test_swe18_defaults_to_unified_budget_and_plore_ploit(self):
        with patch("run_swebench_18tasks.run_swebench.main", return_value=0) as run:
            self.assertEqual(run_swebench_18tasks.main(["--dry-run"]), 0)
        args = run_swebench.build_parser().parse_args(run.call_args.args[0])
        self.assertEqual((args.sample_size, args.max_iterations, args.max_tool_calls), (18, 24, 80))
        self.assertEqual(args.budget_multiplier, 1)
        self.assertEqual((args.base_children_per_node, args.max_children_per_node), (3, 6))
        self.assertTrue(args.run_id.startswith("best-fgs-swe18-"))
        self.assertTrue(str(args.selection_file).endswith("dev18-selection.json"))

    def test_terminal_mock_execution_forwards_eight_and_saves_metrics(self):
        result = {
            "n_total_trials": 8,
            "stats": {
                "n_completed_trials": 8, "n_errored_trials": 0,
                "evals": {"test": {"n_trials": 8, "reward_stats": {"reward": {"1.0": ["a", "b"]}}}},
            },
        }
        agent_rows = [{
            "interaction_rounds": i + 1, "succeeded": i < 2,
            "post_hoc_indicators": {"knowledge_reuse_rate": 0.5},
        } for i in range(8)]
        args = [
            "--selection-file", str(self.root / "tb.json"),
            "--sample-seed", "7", "--agent-log-lines", "0",
            "--skip-preflight",
        ]
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-only"}), patch("run_terminal_bench_tenth._load_all_task_names", return_value=self.tb_population), patch("run_terminal_bench._ensure_unique_job_name", return_value="unit-test-job"), patch("run_terminal_bench._prepare_images", return_value=0), patch("run_terminal_bench._to_wsl_path", return_value="/unit-test/project"), patch("run_terminal_bench._run_streaming", return_value=(0, [])) as run, patch("run_terminal_bench._cleanup_job_containers", return_value=[]), patch("run_terminal_bench._read_wsl_json", return_value=result), patch("run_terminal_bench._read_terminal_agent_results", return_value=agent_rows), patch("run_terminal_bench._write_wsl_json") as save, patch("builtins.print") as printer:
            self.assertEqual(run_terminal_bench_tenth.main(args), 0)
        summary = next(
            call.args[2]
            for call in save.call_args_list
            if str(call.args[1]).endswith("interaction-summary.json")
        )
        self.assertEqual(summary["average_interaction_rounds"], 4.5)
        self.assertEqual(summary["research_metrics"]["knowledge_reuse_rate"]["mean"], 0.5)
        selected = summary["development_selection"]["task_ids"]
        self.assertEqual(len(selected), 8)
        command = run.call_args.args[0][-1]
        self.assertIn("budget_multiplier=1.0", command)
        self.assertIn("max_iterations=24", command)
        self.assertIn("max_tool_calls=80", command)
        self.assertIn("--max-retries 0", command)
        self.assertIn("--n-attempts 1", command)
        for task_id in selected:
            self.assertIn(task_id, command)
        rendered = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        self.assertIn("端到端通过率：25.0%", rendered)
        self.assertIn("知识复用率：50.00%", rendered)

    def test_development_entries_reject_selection_override_and_frozen_bypass(self):
        cases = [
            (run_swebench_18tasks.main, ["--sample-size=4"]),
            (run_swebench_18tasks.main, ["--instance-id=anything"]),
            (run_swebench_18tasks.main, ["--allow-frozen-test-set"]),
            (run_swebench_18tasks.main, ["--dataset=wrong"]),
            (run_terminal_bench_tenth.main, ["--n-tasks=3"]),
            (run_terminal_bench_tenth.main, ["--task-name=anything"]),
            (run_terminal_bench_tenth.main, ["--allow-frozen-test-set"]),
            (run_terminal_bench_tenth.main, ["--dataset=wrong"]),
            (run_swebench_tenth.main, ["--sample-size=4"]),
            (run_swebench_tenth.main, ["--allow-frozen-test-set"]),
            (run_swebench_2random_tasks.main, ["--sample-fraction=0.2"]),
            (run_swebench_2random_tasks.main, ["--instance-id=anything"]),
            (run_terminal_bench_2random_tasks.main, ["--n-tasks=3"]),
            (run_terminal_bench_2random_tasks.main, ["--task-name=anything"]),
            (run_terminal_bench_2random_tasks.main, ["--allow-frozen-test-set"]),
            (run_terminal_bench_2random_tasks.main, ["--dataset=wrong"]),
        ]
        for entry, args in cases:
            with self.subTest(args=args), patch("sys.stderr", new=io.StringIO()):
                self.assertEqual(entry(args), 2)

    def test_abbreviated_flags_cannot_bypass_guard(self):
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as error:
            run_swebench_18tasks.main(["--allow-frozen-test"])
        self.assertEqual(error.exception.code, 2)

    def test_bad_frozen_checksum_stops_before_discovery(self):
        checksum = self.root / "wrong.sha256"
        checksum.write_text("0" * 64, encoding="ascii")
        with patch("benchmark_splits.FROZEN_CHECKSUM", checksum), patch("run_swebench._load_all_instance_ids") as discover, patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(run_swebench_18tasks.main(["--dry-run"]), 1)
            discover.assert_not_called()

    def test_swe_mock_execution_and_resume_use_the_same_eighteen(self):
        args = [
            "--results-dir", str(self.root), "--run-id", "test18",
            "--sample-seed", "7", "--skip-preflight",
        ]

        def fake_run(_args, **kwargs):
            instance_id = kwargs["instance_id"]
            return (
                {"instance_id": instance_id, "model_name_or_path": "test", "model_patch": "diff"},
                {"instance_id": instance_id, "agent_succeeded": True, "agent_interaction_rounds": 2},
            )

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-only"}), patch("run_swebench._load_all_instance_ids", return_value=self.swe_population), patch("run_swebench._load_public_tasks", return_value={item: "fix" for item in self.swe_population}), patch("run_swebench._run_one_instance", side_effect=fake_run) as run, patch("run_swebench._run_official_harness", return_value=0) as harness, patch("builtins.print"):
            self.assertEqual(run_swebench_18tasks.main(args), 0)
            self.assertEqual(run.call_count, 18)
            self.assertEqual(run.call_args.args[0].max_iterations, 24)
            self.assertEqual(run.call_args.args[0].max_tool_calls, 80)
            self.assertEqual(run.call_args.args[0].budget_multiplier, 1)
            selected = harness.call_args.kwargs["instance_ids"]
            run.reset_mock()
            self.assertEqual(run_swebench_18tasks.main(args + ["--resume"]), 0)
            run.assert_not_called()
            self.assertEqual(harness.call_args.kwargs["instance_ids"], selected)
            self.assertEqual(run_swebench_18tasks.main(args), 2)  # never overwrite results
        result = json.loads((self.root / "interaction-summary-test18.json").read_text(encoding="utf-8"))
        self.assertEqual(result["average_interaction_rounds"], 2)
        self.assertEqual(result["recorded_task_count"], 18)
        self.assertIn("research_metrics", result)

    def test_resume_requires_run_id_and_existing_record(self):
        with patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(run_swebench_18tasks.main(["--resume"]), 2)
            self.assertEqual(run_swebench_18tasks.main([
                "--resume", "--run-id", "missing", "--results-dir", str(self.root),
            ]), 1)

    def test_research_metrics_exclude_missing_values_and_print_all_four(self):
        summary = summarize_research_metrics([
            {"post_hoc_indicators": {"knowledge_reuse_rate": 0.2}},
            {"post_hoc_indicators": {"knowledge_reuse_rate": 0.8}},
            {"post_hoc_indicators": {"knowledge_reuse_rate": float("nan")}},
            {"post_hoc_indicators": None},
        ])
        self.assertEqual(summary["knowledge_reuse_rate"], {"mean": 0.5, "recorded_task_count": 2})
        self.assertIsNone(summary["effective_exploration_ratio"]["mean"])
        with patch("builtins.print") as printer:
            print_research_metrics(summary)
        rendered = "\n".join(str(call.args[0]) for call in printer.call_args_list)
        for label in ("最终语义覆盖率", "有效探索比例", "知识复用率", "已确认可复用调用率", "N/A", "50.00%"):
            self.assertIn(label, rendered)

    def test_tool_efficiency_never_pools_legacy_metric_versions(self):
        current = {"trace_complete": True, "metric_version": "cli-comparison-v3",
                   "redundancy_version": "confirmed-reusable-call-v2",
                   "tool_calls": 10, "confirmed_reusable_calls": 2,
                   "unclassified_tool_calls": 3}
        legacy = {"trace_complete": True, "metric_version": "cli-comparison-v1",
                  "tool_calls": 100, "confirmed_reusable_calls": 100,
                  "unclassified_tool_calls": 0}
        result = summarize_research_metrics([
            {"comparison_metrics": current}, {"comparison_metrics": legacy},
        ])["tool_efficiency"]
        self.assertEqual(result["recorded_task_count"], 1)
        self.assertEqual(result["tool_calls"], 10)
        self.assertEqual(result["confirmed_reusable_call_rate"], 0.2)
        self.assertEqual(result["classification_coverage"], 0.7)


if __name__ == "__main__":
    unittest.main()
