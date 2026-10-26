"""Experience-mode wiring uses only mocked model calls and local toy results."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bestfgs import __main__ as cli
from examples.demo_counter import run_demo


class ExperienceCLITests(unittest.TestCase):
    def test_parser_defaults_to_conditioned_and_rejects_unknown_modes(self):
        arguments = ["--goal", "repair", "--workspace", "."]
        self.assertEqual(cli.build_parser().parse_args(arguments).experience_mode, "conditioned")
        for mode in ("off", "legacy", "conditioned"):
            self.assertEqual(cli.build_parser().parse_args([*arguments, "--experience-mode", mode]).experience_mode, mode)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.build_parser().parse_args([*arguments, "--experience-mode", "automatic"])

    def test_cli_passes_mode_to_runtime_and_policy_and_emits_report(self):
        base_result = run_demo()
        for mode in ("off", "legacy", "conditioned"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory) / "seed"
                workspace.mkdir()
                report = {"mode": mode, "records_observed": 2}
                records = ({"evidence_id": "observed-command-1", "task_id": "fixture-task"},)
                result = replace(base_result, experience_mode=mode, experience_report=report,
                                 task_experiences=records,
                                 delivery={"has_patch": True, "local_validation_passed": False})
                output = io.StringIO()
                with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only", "DEEPSEEK_MODEL": "test-model"}), \
                     patch.object(cli, "TaskRunner") as runner, \
                     patch.object(cli, "RetracPolicyAdapter") as policy, redirect_stdout(output):
                    runner.return_value.run.return_value = result
                    policy.return_value.model_usage_summary.return_value = {}
                    code = cli.main(["--engine", "legacy", "--goal", "repair", "--workspace", str(workspace),
                        "--run-root", str(Path(directory) / "runs"), "--provider", "deepseek",
                        "--experience-mode", mode, "--quiet"])
                    self.assertEqual(code, 0)
                    self.assertEqual(policy.call_args.kwargs["experience_mode"], mode)
                    self.assertEqual(runner.call_args.kwargs["config"].experience_mode, mode)
                payload = json.loads(output.getvalue())
                self.assertEqual(payload["experience_mode"], mode)
                self.assertEqual(payload["experience_report"], report)
                self.assertEqual(payload["task_experiences"], list(records))
                self.assertIsNone(payload["official_resolved"])

    def test_checkpoint_fallback_preserves_experience_report(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "seed"
            workspace.mkdir()
            run_root = Path(directory) / "runs"
            run_root.mkdir()
            report = {"mode": "conditioned", "records_observed": 3}
            checkpoint = {"experience_mode": "conditioned", "experience_report": report,
                          "task_experiences": [{"evidence_id": "checkpoint-observation"}],
                          "delivery": {"has_patch": True}, "transitions_completed": 1}
            (run_root / "search_checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
            output = io.StringIO()
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-only", "DEEPSEEK_MODEL": "test-model"}), \
                 patch.object(cli, "TaskRunner") as runner, \
                 patch.object(cli, "RetracPolicyAdapter") as policy, redirect_stdout(output):
                runner.return_value.run.side_effect = RuntimeError("interrupted locally")
                policy.return_value.model_usage_summary.return_value = {}
                code = cli.main(["--engine", "legacy", "--goal", "repair", "--workspace", str(workspace),
                    "--run-root", str(run_root), "--provider", "deepseek", "--quiet"])
            payload = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertEqual(payload["experience_mode"], "conditioned")
            self.assertEqual(payload["experience_report"], report)
            self.assertEqual(payload["task_experiences"], checkpoint["task_experiences"])
            self.assertEqual(payload["stop_reason"], "runtime_error_with_checkpoint")
            self.assertFalse(payload["submitted"])
            self.assertFalse(payload["succeeded"])


if __name__ == "__main__":
    unittest.main()
