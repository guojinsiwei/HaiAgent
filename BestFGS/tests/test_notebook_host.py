import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import host_runtime
import notebook_preflight
import run_swebench
import run_terminal_bench
import run_terminal_bench_tenth


class NotebookHostTests(unittest.TestCase):
    def test_linux_host_never_launches_wsl_for_shell_or_paths(self):
        with patch("sys.platform", "linux"), patch("subprocess.run") as run:
            for runner in (run_swebench, run_terminal_bench):
                self.assertEqual(runner._wsl_command("unused", "echo ok"), ["bash", "-lc", "echo ok"])
                self.assertEqual(runner._to_wsl_path("unused", Path(".")), str(Path(".").resolve()))
            run.assert_not_called()
            self.assertEqual(host_runtime.default_docker_executable(), "docker")

    def test_windows_commands_remain_compatible(self):
        with patch("sys.platform", "win32"):
            self.assertEqual(host_runtime.linux_command("Ubuntu", "test", "-e", "/tmp/job"),
                             ["wsl.exe", "-d", "Ubuntu", "--", "test", "-e", "/tmp/job"])

    def test_linux_result_read_write_and_job_checks_use_native_commands(self):
        with patch("sys.platform", "linux"), patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "[]", "")) as run:
            self.assertEqual(run_terminal_bench._read_terminal_agent_results("unused", "/tmp/job"), [])
            self.assertEqual(run.call_args.args[0][0], "python3")
            run_terminal_bench._write_wsl_json("unused", "/tmp/result.json", {"ok": True})
            self.assertEqual(run.call_args.args[0][0], "python3")
            self.assertTrue(run_terminal_bench._wsl_job_directory_exists("unused", "/tmp", "job"))
            self.assertEqual(run.call_args.args[0], ["test", "-e", "/tmp/jobs/job"])

    def test_linux_harbor_discovery_uses_its_interpreter(self):
        responses = [subprocess.CompletedProcess([], 0, "/opt/harbor/bin/harbor\n", ""),
                     subprocess.CompletedProcess([], 0, "#!/opt/harbor/bin/python\n", ""),
                     subprocess.CompletedProcess([], 0, '["task-a"]', "")]
        args = run_terminal_bench.build_parser().parse_args([])
        with patch("sys.platform", "linux"), patch("subprocess.run", side_effect=responses) as run:
            self.assertEqual(run_terminal_bench_tenth._load_all_task_names(args), ["task-a"])
            self.assertEqual(run.call_args_list[1].args[0], ["head", "-n", "1", "/opt/harbor/bin/harbor"])
            self.assertEqual(run.call_args_list[2].args[0][0], "/opt/harbor/bin/python")

    def test_preflight_does_not_expose_keys_or_claim_benchmark_ready(self):
        secret = "notebook-unit-test-secret"
        with tempfile.TemporaryDirectory() as directory, patch("sys.platform", "linux"), patch.dict(os.environ, {"DEEPSEEK_API_KEY": secret}), patch("shutil.which", side_effect=lambda name: f"/bin/{name}"), patch("subprocess.run") as run:
            report = notebook_preflight.inspect_environment(Path(directory))
            self.assertTrue(report["agent_runtime_ready"])
            self.assertTrue(report["credential_present"]["DEEPSEEK_API_KEY"])
            self.assertFalse(report["official_benchmarks_ready"])
            self.assertNotIn(secret, json.dumps(report))
            run.assert_not_called()
            self.assertEqual(run_terminal_bench._wsl_env_with_secret("DEEPSEEK_API_KEY")["DEEPSEEK_API_KEY"], secret)


if __name__ == "__main__":
    unittest.main()
