import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from benchmark_metrics import summarize_official_interactions, swe_official_outcomes, terminal_official_outcomes

import run_swebench
import run_swebench_2tasks
import run_terminal_bench
import run_terminal_bench_tenth
from benchmark_splits import (
    frozen_swebench_ids,
    frozen_terminal_task_names,
)


class BenchmarkRunnerTests(unittest.TestCase):
    def test_official_rounds_join_by_id_and_keep_unknowns_separate(self):
        rows = [
            {"id": "fp", "interaction_rounds": 8, "succeeded": True},
            {"id": "tp", "interaction_rounds": 4, "succeeded": True},
            {"id": "fn", "interaction_rounds": 24, "succeeded": False},
            {"id": "unknown", "interaction_rounds": 2, "succeeded": False},
        ]
        summary = summarize_official_interactions(
            rows, {"tp": True, "fn": True, "fp": False}, id_key="id", selected_count=5,
        )
        self.assertEqual(summary["average_successful_interaction_rounds"], 14)
        self.assertEqual(summary["average_failed_interaction_rounds"], 8)
        self.assertEqual(summary["average_interaction_rounds"], 9.5)
        self.assertEqual(summary["agent_diagnostic"]["average_successful_interaction_rounds"], 6)
        self.assertEqual(summary["official_ungraded_task_count"], 2)
        self.assertEqual(summary["agent_vs_official"]["false_positive"], 1)
        self.assertEqual(summary["agent_vs_official"]["false_negative"], 1)

    def test_official_label_extractors_ignore_missing_or_invalid_scores(self):
        self.assertEqual(swe_official_outcomes({
            "submitted_ids": ["ok", "empty", "bad"], "resolved_ids": ["ok"], "unresolved_ids": ["bad"],
        }), {"ok": True, "empty": None, "bad": False})
        report = {"stats": {"evals": {"model": {"reward_stats": {"reward": {
            "1.0": ["ok"], "0.0": ["bad"], "NaN": ["unknown"],
        }}}}}}
        self.assertEqual(terminal_official_outcomes(report), {"ok": True, "bad": False})

    def test_two_task_entry_uses_same_tasks_and_only_runs_this_project(self):
        with patch("run_swebench_2tasks.run_swebench.main", return_value=0) as run:
            self.assertEqual(run_swebench_2tasks.main(["--dry-run", "--max-children-per-node", "6"]), 0)
        args = run_swebench.build_parser().parse_args(run.call_args.args[0])
        self.assertEqual(tuple(args.instance_id), run_swebench_2tasks.INSTANCE_IDS)
        self.assertEqual(args.selection_mode, "plore_ploit")
        self.assertEqual(args.max_children_per_node, 6)
        self.assertTrue(args.run_id.startswith("best-fgs-two-"))

    def test_two_task_entry_rejects_overriding_task_selection(self):
        with patch("run_swebench_2tasks.run_swebench.main") as run, patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(run_swebench_2tasks.main(["--instance-id=other"]), 2)
            run.assert_not_called()

    def test_interaction_round_summary_records_overall_and_success_averages(self) -> None:
        rows = [
            {"agent_interaction_rounds": 2, "agent_succeeded": True},
            {"agent_interaction_rounds": 4, "agent_succeeded": False},
            {"agent_interaction_rounds": 6, "agent_succeeded": True},
            {"agent_interaction_rounds": None, "agent_succeeded": False},
        ]

        summary = run_swebench.summarize_interaction_rounds(
            rows,
            rounds_key="agent_interaction_rounds",
            success_key="agent_succeeded",
        )

        self.assertEqual(summary["task_count"], 4)
        self.assertEqual(summary["recorded_task_count"], 3)
        self.assertEqual(summary["total_interaction_rounds"], 12)
        self.assertEqual(summary["average_interaction_rounds"], 4.0)
        self.assertEqual(summary["average_successful_interaction_rounds"], 4.0)
        self.assertEqual(summary["average_failed_interaction_rounds"], 4.0)

    def test_swebench_writes_interaction_round_summary_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interaction-summary.json"
            summary = run_swebench._write_interaction_summary(
                path,
                [
                    {"agent_interaction_rounds": 1, "agent_succeeded": True},
                    {"agent_interaction_rounds": 3, "agent_succeeded": True},
                ],
            )
            saved = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(summary["average_interaction_rounds"], 2.0)
        self.assertEqual(saved, summary)

    def test_terminal_summary_displays_interaction_round_averages(self) -> None:
        with patch("builtins.print") as printer:
            run_terminal_bench._print_summary(
                {"n_total_trials": 0, "stats": {"evals": {}}},
                "/jobs/test/result.json",
                interaction_summary={
                    "average_interaction_rounds": 3.5,
                    "average_successful_interaction_rounds": 2.0,
                },
                interaction_summary_path="/jobs/test/interaction-summary.json",
            )

        rendered = "\n".join(
            str(call.args[0]) for call in printer.call_args_list if call.args
        )
        self.assertIn("平均交互轮次：3.5", rendered)
        self.assertIn("成功任务平均交互轮次：2.0", rendered)
        self.assertIn("interaction-summary.json", rendered)

    def test_frozen_test_set_v1_has_fixed_unique_sizes(self) -> None:
        swe_ids = frozen_swebench_ids()
        terminal_names = frozen_terminal_task_names()

        self.assertEqual(len(swe_ids), 50)
        self.assertEqual(len(set(swe_ids)), 50)
        self.assertEqual(len(terminal_names), 9)
        self.assertEqual(len(set(terminal_names)), 9)

    def test_swe_development_sampling_excludes_frozen_test_set(self) -> None:
        frozen = list(frozen_swebench_ids())
        development = [f"project__issue-{index}" for index in range(50)]

        with patch(
            "run_swebench._load_all_instance_ids",
            return_value=[*frozen, *development],
        ), patch(
            "run_swebench._random_sample",
            wraps=run_swebench._random_sample,
        ) as sampler, patch("builtins.print"):
            code = run_swebench.main(
                ["--sample-seed", "7", "--dry-run"]
            )

        self.assertEqual(code, 0)
        sampled_population = set(sampler.call_args.args[0])
        self.assertTrue(sampled_population)
        self.assertTrue(sampled_population.isdisjoint(frozen))

    def test_terminal_explicit_frozen_task_is_rejected(self) -> None:
        protected = frozen_terminal_task_names(bare=True)[0]
        args = run_terminal_bench.build_parser().parse_args(
            ["--task-name", protected, "--dry-run"]
        )

        with patch("builtins.print"):
            code = run_terminal_bench.run(args)

        self.assertEqual(code, 2)

    def test_terminal_tenth_excludes_frozen_test_set(self) -> None:
        frozen = list(frozen_terminal_task_names())
        development = [f"terminal-bench/dev-task-{index}" for index in range(10)]

        with tempfile.TemporaryDirectory() as directory, patch(
            "run_terminal_bench_tenth._load_all_task_names",
            return_value=[*frozen, *development],
        ), patch(
            "run_terminal_bench_tenth.terminal_runner.run",
            return_value=0,
        ) as run:
            code = run_terminal_bench_tenth.main([
                "--sample-seed", "7", "--selection-file",
                str(Path(directory) / "selection.json"),
            ])

        self.assertEqual(code, 0)
        selected = set(run.call_args.kwargs["task_names"])
        self.assertEqual(len(selected), 1)
        self.assertTrue(selected.isdisjoint(frozen_terminal_task_names(bare=True)))

    def test_benchmark_image_pull_defaults_are_ten(self) -> None:
        self.assertEqual(
            run_swebench.build_parser().parse_args([]).image_pull_attempts,
            10,
        )

    def test_fused_benchmark_entries_use_unified_budgets_without_auto_extension(self) -> None:
        swe_args = run_swebench.build_parser().parse_args([])
        terminal_args = run_terminal_bench.build_parser().parse_args([])

        self.assertEqual(swe_args.selection_mode, "plore_ploit")
        self.assertEqual(terminal_args.selection_mode, "plore_ploit")
        self.assertEqual((swe_args.max_iterations, swe_args.max_tool_calls), (24, 80))
        self.assertEqual((terminal_args.max_iterations, terminal_args.max_tool_calls), (24, 80))
        self.assertEqual(swe_args.budget_multiplier, 1.0)
        self.assertEqual(terminal_args.budget_multiplier, 1.0)
        self.assertEqual(terminal_args.max_retries, 0)
        self.assertEqual(swe_args.base_children_per_node, 3)
        self.assertEqual(terminal_args.base_children_per_node, 3)
        self.assertEqual(swe_args.max_children_per_node, 6)
        self.assertEqual(terminal_args.max_children_per_node, 6)
        self.assertEqual(
            run_terminal_bench.build_parser().parse_args([]).image_pull_attempts,
            10,
        )

    def test_swe_random_tenth_is_reproducible_and_has_50_of_500(self) -> None:
        population = [f"project__issue-{index}" for index in range(500)]

        first = run_swebench._random_sample(
            population, fraction=0.1, seed=20260830
        )
        repeated = run_swebench._random_sample(
            population, fraction=0.1, seed=20260830
        )
        different = run_swebench._random_sample(
            population, fraction=0.1, seed=20260831
        )

        self.assertEqual(len(first), 50)
        self.assertEqual(len(set(first)), 50)
        self.assertEqual(first, repeated)
        self.assertNotEqual(first, different)

    def test_direct_cli_disables_extension_and_keeps_original_complexity_schedule(self) -> None:
        from cli_retrac_mcts.__main__ import build_parser
        from cli_retrac_mcts.mcts import adapt_search_budget

        args = build_parser().parse_args(["--goal", "test", "--workspace", "."])
        self.assertEqual((args.max_iterations, args.max_tool_calls), (24, 80))
        self.assertEqual(args.budget_multiplier, 1.0)
        complex_text = "a" * 1700 + "\nTraceback (most recent call last)"
        for base, expected in (((8, 24), (11, 33)), ((24, 80), (33, 108))):
            budget = adapt_search_budget(
                complex_text, base_iterations=base[0], base_tool_calls=base[1],
            )
            self.assertEqual(budget.complexity, "complex")
            self.assertEqual((budget.max_iterations, budget.max_total_tool_calls), expected)

    def test_swe_sample_size_can_explicitly_override_tenth(self) -> None:
        selected = run_swebench._random_sample(
            [f"task-{index}" for index in range(100)],
            fraction=0.1,
            seed=7,
            sample_size=3,
        )

        self.assertEqual(len(selected), 3)

    def test_terminal_random_tenth_rounds_89_tasks_up_to_9(self) -> None:
        population = [f"terminal-bench/task-{index}" for index in range(89)]

        first = run_terminal_bench_tenth._random_sample(
            population, seed=20260830
        )
        repeated = run_terminal_bench_tenth._random_sample(
            population, seed=20260830
        )

        self.assertEqual(len(first), 9)
        self.assertEqual(len(set(first)), 9)
        self.assertEqual(first, repeated)

    def test_terminal_original_one_task_entry_is_preserved(self) -> None:
        args = run_terminal_bench.build_parser().parse_args(
            ["--n-tasks", "1", "--dry-run"]
        )

        with patch("builtins.print"):
            code = run_terminal_bench.run(args)

        self.assertEqual(code, 0)
        self.assertEqual(
            run_terminal_bench.DEFAULT_TASK_NAMES[0], "make-mips-interpreter"
        )

    def test_terminal_explicit_single_task_can_select_known_regression_case(self) -> None:
        args = run_terminal_bench.build_parser().parse_args(
            ["--task-name", "circuit-fibsqrt", "--dry-run"]
        )

        with patch("builtins.print") as printer:
            code = run_terminal_bench.run(args)

        rendered = "\n".join(
            str(call.args[0]) for call in printer.call_args_list if call.args
        )
        self.assertEqual(code, 0)
        self.assertIn("terminal-bench/circuit-fibsqrt", rendered)
        self.assertNotIn("terminal-bench/make-mips-interpreter", rendered)

    def test_terminal_external_selection_bypasses_fixed_subset_limit(self) -> None:
        args = run_terminal_bench.build_parser().parse_args(
            ["--n-tasks", "999", "--dry-run"]
        )

        with patch("builtins.print"):
            code = run_terminal_bench.run(
                args,
                task_names=["outside-fixed-list"],
                selection_summary="随机抽样测试",
            )

        self.assertEqual(code, 0)

    def test_terminal_uses_fail_fast_model_request_defaults(self) -> None:
        args = run_terminal_bench.build_parser().parse_args([])

        self.assertEqual(args.model_timeout, 90)
        self.assertEqual(args.model_max_wall_time, 600)
        self.assertEqual(args.model_request_attempts, 4)
        self.assertEqual(args.agent_log_lines, 2000)

    def test_terminal_progress_filter_keeps_key_agent_events(self) -> None:
        self.assertTrue(
            run_terminal_bench._should_show_agent_progress(
                "12:00:00 | [MCTS] 迭代 2/24，已使用工具调用 4/80"
            )
        )
        self.assertTrue(
            run_terminal_bench._should_show_agent_progress(
                "12:00:00 | [API] 正在请求模型（网络尝试 1/8）"
            )
        )
        self.assertTrue(
            run_terminal_bench._should_show_agent_progress(
                "12:00:01 | [API] 模型响应已收到并解析为JSON"
            )
        )
        self.assertTrue(
            run_terminal_bench._should_show_agent_progress(
                "12:00:30 | [API] 已收到流式活动，模型仍在思考（已等待30秒）"
            )
        )
        self.assertTrue(
            run_terminal_bench._should_show_agent_progress(
                "12:00:03 | [API] 4.0秒后重试"
            )
        )
        self.assertTrue(
            run_terminal_bench._should_show_agent_progress(
                "12:00:04 | [环境] 命令结束：return_code=0，成功=True"
            )
        )
        self.assertTrue(
            run_terminal_bench._should_show_agent_progress(
                "12:00:05 | [上下文] 模型视图5191字符（上限14000）"
            )
        )
        self.assertFalse(
            run_terminal_bench._should_show_agent_progress(
                "Harbor network policy warning"
            )
        )

    def test_terminal_tail_script_follows_each_trial_progress_file(self) -> None:
        script = run_terminal_bench._agent_log_tail_script(
            "/home/research/benchmark-runs/terminal-bench/jobs/retrac-test"
        )

        self.assertIn("*/agent/retrac_progress.log", script)
        self.assertIn("declare -A seen_lines", script)
        self.assertIn("trial_name=${progress_file#", script)
        self.assertIn("sleep 1", script)

    def test_terminal_progress_relay_limits_each_trial(self) -> None:
        progress = io.StringIO(
            "trial-a\t12:00:00 | [任务] 已加载配置\n"
            "trial-a\t12:00:01 | [MCTS] 迭代 1/24\n"
            "trial-a\t12:00:02 | [MCTS] 迭代 2/24\n"
        )
        fake_process = SimpleNamespace(stdout=progress)

        with patch("builtins.print") as printer:
            run_terminal_bench._relay_agent_progress(fake_process, 2)

        rendered = [call.args[0] for call in printer.call_args_list]
        self.assertEqual(len(rendered), 3)
        self.assertIn("[Agent:trial-a]", rendered[0])
        self.assertIn("已达到实时日志上限 2 行", rendered[2])

    def test_terminal_cleanup_is_scoped_to_current_job_trials(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="circuit-fibsqrt__abc__env-main-1\n",
            stderr="",
        )
        with patch("run_terminal_bench.subprocess.run", return_value=completed) as run:
            removed = run_terminal_bench._cleanup_job_containers(
                "Ubuntu",
                "/home/research/benchmark-runs/terminal-bench",
                "retrac-test-job",
            )

        self.assertEqual(removed, ["circuit-fibsqrt__abc__env-main-1"])
        self.assertEqual(
            run.call_args.args[0],
            ["wsl.exe", "-d", "Ubuntu", "--", "bash", "-s", "--"],
        )
        shell_script = run.call_args.kwargs["input"]
        if isinstance(shell_script, bytes):
            shell_script = shell_script.decode("utf-8")
        self.assertIn("retrac-test-job", shell_script)
        self.assertIn('"${trial}__env-"*', shell_script)
        self.assertIn('cat "$proc/comm"', shell_script)
        self.assertNotIn("docker system prune", shell_script)

    def test_terminal_job_name_collision_uses_unique_name(self) -> None:
        with patch(
            "run_terminal_bench._wsl_job_directory_exists",
            side_effect=[True, False],
        ) as exists, patch("builtins.print") as printer:
            resolved = run_terminal_bench._ensure_unique_job_name(
                "Ubuntu",
                "/home/research/benchmark-runs/terminal-bench",
                "fixed-job",
            )

        self.assertNotEqual(resolved, "fixed-job")
        self.assertTrue(resolved.startswith("fixed-job-retry-"))
        self.assertEqual(exists.call_count, 2)
        self.assertIn("为保留旧结果", printer.call_args.args[0])

    def test_swebench_uses_checkpoint_when_final_result_is_empty(self) -> None:
        args = SimpleNamespace(
            max_iterations=8,
            max_tool_calls=24,
            model_timeout=90,
            model_max_wall_time=600,
            model_request_attempts=4,
            model_parse_attempts=3,
        )

        shell = run_swebench._agent_shell_command(
            args,
            problem_statement="repair the bug",
            provider="deepseek",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            key_name="DEEPSEEK_API_KEY",
        )

        self.assertIn("search_checkpoint.json", shell)
        self.assertIn("cp /tmp/cli_retrac_mcts/swebench-task/search_checkpoint.json", shell)
        self.assertIn("--model-max-wall-time 600", shell)
        self.assertIn("--selection-mode plore_ploit", shell)
        self.assertNotIn("--exploit-failures-before-explore", shell)
        self.assertIn("--budget-multiplier 1.0", shell)
        self.assertIn("--base-children-per-node 3", shell)
        self.assertIn("--max-children-per-node 6", shell)
        self.assertNotIn("--progressive-widening-max-children", shell)

    def test_swebench_cleans_windows_newlines_from_api_key(self) -> None:
        args = SimpleNamespace(
            max_iterations=8,
            max_tool_calls=24,
            model_timeout=90,
            model_max_wall_time=600,
            model_request_attempts=4,
            model_parse_attempts=3,
        )

        shell = run_swebench._agent_shell_command(
            args,
            problem_statement="repair the bug",
            provider="deepseek",
            model="deepseek-v4-flash",
            base_url="https://api.deepseek.com",
            key_name="DEEPSEEK_API_KEY",
        )

        self.assertEqual(run_swebench._clean_api_key("  secret\r\n"), "secret")
        self.assertIn("RETRAC_API_KEY=${RETRAC_API_KEY//$'\\r'/}", shell)

    def test_swebench_resume_retries_only_incomplete_and_preserves_old_patch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "resume-status"
            instance_ids = ["example__project-1", "example__project-2"]
            (root / f"selection-{run_id}.json").write_text(
                json.dumps({
                    "run_id": run_id,
                    "dataset": run_swebench.DEFAULT_DATASET,
                    "instance_ids": instance_ids,
                }),
                encoding="utf-8",
            )
            run_swebench._write_jsonl(root / f"predictions-{run_id}.jsonl", [
                {"instance_id": instance_ids[0], "model_name_or_path": "old", "model_patch": "done"},
                {"instance_id": instance_ids[1], "model_name_or_path": "old", "model_patch": "checkpoint"},
            ])
            run_swebench._write_metadata(root / f"agent-results-{run_id}.json", [
                {"instance_id": instance_ids[0], "execution_status": "completed"},
                {"instance_id": instance_ids[1], "execution_status": "retryable_checkpoint"},
            ])
            failed_retry = (
                {"instance_id": instance_ids[1], "model_name_or_path": "new", "model_patch": ""},
                {"instance_id": instance_ids[1], "execution_status": "retryable_error", "error": "image"},
            )
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "unit-test-only"}), patch(
                "run_swebench._load_public_tasks",
                return_value={instance_ids[1]: "repair"},
            ) as load_tasks, patch(
                "run_swebench._run_one_instance", return_value=failed_retry
            ) as run_one, patch("builtins.print"):
                code = run_swebench.main([
                    "--resume", "--run-id", run_id,
                    "--results-dir", str(root), "--skip-evaluation",
                ])

            self.assertEqual(code, 0)
            load_tasks.assert_called_once()
            self.assertEqual(load_tasks.call_args.args[1], [instance_ids[1]])
            run_one.assert_called_once()
            predictions = run_swebench._read_existing_predictions(
                root / f"predictions-{run_id}.jsonl"
            )
            self.assertEqual(len(predictions), 2)
            self.assertEqual(predictions[1]["model_patch"], "checkpoint")
            metadata = run_swebench._read_existing_metadata(
                root / f"agent-results-{run_id}.json"
            )
            self.assertTrue(metadata[1]["preserved_previous_patch"])
            self.assertEqual(metadata[1]["execution_status"], "retryable_checkpoint")

    def test_execution_status_classifiers_do_not_confuse_checkpoint_with_completion(self) -> None:
        self.assertEqual(
            run_swebench._classify_swe_execution(
                {"agent_stop_reason": "running", "error": "interrupted"},
                {"model_patch": "diff"},
            ),
            "retryable_checkpoint",
        )
        self.assertEqual(
            run_swebench._classify_swe_execution(
                {"agent_stop_reason": "tool_call_budget_exhausted"},
                {"model_patch": ""},
            ),
            "completed_no_candidate",
        )
        self.assertEqual(
            run_terminal_bench._classify_terminal_execution({
                "stop_reason": "runtime_error_with_checkpoint",
                "agent_exit_code": 1,
                "best_workspace": "/tmp/candidate",
            }),
            "retryable_checkpoint",
        )


if __name__ == "__main__":
    unittest.main()
