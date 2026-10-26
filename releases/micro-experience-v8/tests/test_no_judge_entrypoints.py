"""Production entrypoints must not enable an independent result-judging LLM."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
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
import run_swebench
import run_terminal_bench
from bestfgs import __main__ as cli
from examples.demo_counter import run_demo


class NoJudgeEntrypointTests(unittest.TestCase):
    def parsers(self):
        return [(cli.build_parser(), ["--goal", "test", "--workspace", "."]),
                (run_swebench.build_parser(), []), (run_terminal_bench.build_parser(), [])]

    def test_all_production_defaults_off(self):
        for parser, arguments in self.parsers():
            self.assertEqual(parser.parse_args(arguments).success_judge_mode, "off")

    def test_production_cannot_reenable_auditor(self):
        for parser, arguments in self.parsers():
            for mode in ("required", "audit"):
                with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    parser.parse_args([*arguments, "--success-judge-mode", mode])

    def test_cli_ignores_old_judge_credentials_and_constructs_no_auditor(self):
        # Reuse the toy's result shape only. The mocked production result is an
        # artifact delivery, not the toy's historical internal-success verdict.
        result = replace(run_demo(), stop_reason="submitted", delivery={
            "has_patch": True, "status": "submitted", "submitted": True,
            "local_validation_passed": True, "official_resolved": None,
        })
        self.assertFalse(result.succeeded)
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory) / "seed"
            seed.mkdir()
            env = {"DEEPSEEK_API_KEY": "test-only", "DEEPSEEK_MODEL": "test-solver",
                   "SUCCESS_JUDGE_PROVIDER": "invalid-old-provider",
                   "SUCCESS_JUDGE_MODEL": "old-judge",
                   "SUCCESS_JUDGE_API_BASE": "https://unused.example?token=unused"}
            with patch.dict(os.environ, env), patch("bestfgs.success_judge.IndependentSuccessJudge", side_effect=AssertionError("Judge must not be created")) as auditor, patch.object(cli, "TaskRunner") as runner, patch.object(cli, "RetracPolicyAdapter") as policy, redirect_stdout(output):
                runner.return_value.run.return_value = result
                policy.return_value.model_usage_summary.return_value = {}
                code = cli.main(["--goal", "test", "--workspace", str(seed), "--run-root", str(Path(directory) / "runs"), "--provider", "deepseek", "--quiet"])
                self.assertEqual(code, 0)
                auditor.assert_not_called()
                self.assertIsNone(runner.call_args.kwargs["success_judge"])
                self.assertEqual(runner.call_args.kwargs["config"].success_judge_mode, "off")
                self.assertEqual(runner.call_args.kwargs["config"].termination_mode, "explicit_submission")
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["succeeded"])
        self.assertTrue(payload["submitted"])
        self.assertTrue(payload["delivery"]["has_patch"])
        self.assertTrue(payload["local_validation_passed"])
        self.assertIsNone(payload["official_resolved"])
        self.assertEqual(payload["success_judge_calls"], 0)
        self.assertEqual(payload["success_judge_mode"], "off")
        self.assertEqual(payload["success_judge_model"], "off")
        self.assertEqual(payload["success_judge_decisions"], [])
        self.assertNotIn("old-judge", output.getvalue())


if __name__ == "__main__":
    unittest.main()
