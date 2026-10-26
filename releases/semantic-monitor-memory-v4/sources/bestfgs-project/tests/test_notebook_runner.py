from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import run_notebook as notebook
from benchmark_runtime import atomic_write_json
from bestfgs.submission import inspect_git_submission


class NotebookRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "task.txt").write_text("initial", encoding="utf-8")
        self.manifest = self.root / "tasks.json"
        self.output = self.root / "results"
        self.data = {"schema_version": 1, "benchmark": "custom", "tasks": [
            {"id": "task-01", "goal": "Fix task", "workspace": "seed", "success_criteria": ["Test passes"]}
        ]}
        self.write_manifest()

    def write_manifest(self):
        atomic_write_json(self.manifest, self.data)

    def argv(self, *options):
        return ["--task-manifest", str(self.manifest), "--output-root", str(self.output), *options, "--", "--provider", "deepseek"]

    def invoke(self, *options, executor=None):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret-only", "DEEPSEEK_MODEL": "test-model"}), patch.object(notebook, "execute", side_effect=executor or self.fake_agent):
            return notebook.main(self.argv(*options))

    def fake_agent(self, command, directory, env, timeout):
        self.assertNotIn("test-secret-only", " ".join(command))
        self.assertEqual(command[1:3], ["-m", "bestfgs"])
        self.assertIn(str(ROOT / "src"), env["PYTHONPATH"])
        snapshot = directory / "snapshots" / "candidate"
        snapshot.mkdir(parents=True)
        atomic_write_json(directory / "agent-result.json", {"succeeded": True, "best_workspace": str(snapshot)})
        return 0

    def test_batch_artifacts_and_seed_preserved(self):
        self.assertEqual(self.invoke(), 0)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertEqual(state["status"], "completed")
        self.assertTrue(state["agent_succeeded"])
        self.assertFalse(state["official_evaluation"])
        self.assertEqual((self.seed / "task.txt").read_text(), "initial")
        self.assertNotIn("test-secret-only", (self.output / "notebook-run.json").read_text())

    def test_completed_resume_does_not_call_agent(self):
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.invoke("--resume", executor=lambda *args: self.fail("Must skip completed tasks")), 0)

    def test_existing_root_requires_resume(self):
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.invoke(), 2)

    def test_resume_rejects_seed_changes(self):
        self.assertEqual(self.invoke(), 0)
        (self.seed / "task.txt").write_text("changed")
        self.assertEqual(self.invoke("--resume"), 2)

    def test_error_is_retried_in_new_attempt(self):
        self.assertEqual(self.invoke(executor=lambda *args: (_ for _ in ()).throw(OSError("broken"))), 2)
        before = json.loads((self.output / "task-01/status.json").read_text())["attempt"]
        self.assertEqual(self.invoke("--resume"), 0)
        after = json.loads((self.output / "task-01/status.json").read_text())["attempt"]
        self.assertNotEqual(before, after)

    def test_unsolved_is_completed_not_infrastructure_error(self):
        def unsolved(command, directory, env, timeout):
            atomic_write_json(directory / "agent-result.json", {"succeeded": False, "best_workspace": None})
            return 1
        self.assertEqual(self.invoke(executor=unsolved), 0)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertFalse(state["agent_succeeded"])
        self.assertEqual(state["status"], "completed")

    def test_malformed_results_are_errors(self):
        def malformed(command, directory, env, timeout):
            (directory / "agent-result.json").write_text("not json")
            return 0
        self.assertEqual(self.invoke(executor=malformed), 2)

    def test_candidate_path_escape_is_error(self):
        def escape(command, directory, env, timeout):
            atomic_write_json(directory / "agent-result.json", {"succeeded": True, "best_workspace": str(self.seed)})
            return 0
        self.assertEqual(self.invoke(executor=escape), 2)

    def test_interrupt_state_persisted(self):
        self.assertEqual(self.invoke(executor=lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())), 130)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertEqual(state["status"], "interrupted")

    def test_dryrun_is_nonmutating(self):
        self.assertEqual(self.invoke("--dry-run"), 0)
        self.assertFalse(self.output.exists())

    def test_manifest_validation(self):
        for mutation in (
            lambda: self.data["tasks"][0].update(id="../escape"),
            lambda: self.data["tasks"].append(dict(self.data["tasks"][0])),
            lambda: self.data["tasks"][0].update(workspace="missing"),
            lambda: self.data["tasks"][0].update(success_criteria="wrong"),
        ):
            self.setUp()
            mutation()
            self.write_manifest()
            with self.assertRaises(ValueError):
                notebook.load_tasks(self.manifest, self.output)

    def test_output_cannot_be_in_seed(self):
        with self.assertRaises(ValueError):
            notebook.load_tasks(self.manifest, self.seed / "results")

    def test_reserved_and_abbreviated_agent_flags_rejected(self):
        task = notebook.load_tasks(self.manifest, self.output)[1][0]
        with self.assertRaises(ValueError):
            notebook.agent_arguments(task, self.output, ["--workspace=elsewhere"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            notebook.agent_arguments(task, self.output, ["--work", "elsewhere"])

    def test_frozen_guard_is_not_bypassed(self):
        self.data["benchmark"] = "terminal-bench"
        self.write_manifest()
        with patch.object(notebook, "reject_frozen_overlap", side_effect=RuntimeError("protected")) as guard, self.assertRaises(RuntimeError):
            notebook.load_tasks(self.manifest, self.output)
        guard.assert_called_once_with(["task-01"], benchmark="terminal-bench", allow_frozen_test_set=False)

    def test_shared_output_lock(self):
        with notebook.run_lock(self.output):
            with self.assertRaises(ValueError):
                with notebook.run_lock(self.output):
                    pass

    def test_real_python_process_no_docker(self):
        attempt = self.root / "attempt"
        attempt.mkdir()
        self.assertEqual(notebook.execute([sys.executable, "-c", "import json; print(json.dumps({'succeeded':False}))"], attempt, notebook.child_environment(Path(sys.executable)), 5), 0)
        self.assertFalse(json.loads((attempt / "agent-result.json").read_text())["succeeded"])

    def test_separate_task_python_only_changes_path_not_agent_command(self):
        agent = Path(sys.executable)
        task_python = self.root / "task-env" / "bin" / "python"
        task_python.parent.mkdir(parents=True)
        task_python.touch()
        env = notebook.child_environment(agent, task_python)
        self.assertEqual(env["PATH"].split(os.pathsep)[0], str(task_python.parent))
        self.assertEqual(env["PATH"].split(os.pathsep)[1], str(agent.parent))

    def test_missing_task_python_is_rejected(self):
        self.assertEqual(self.invoke("--task-python", str(self.root / "absent")), 2)

    def test_real_process_timeout(self):
        attempt = self.root / "attempt"
        attempt.mkdir()
        with self.assertRaises(subprocess.TimeoutExpired):
            notebook.execute([sys.executable, "-c", "import time; time.sleep(5)"], attempt, notebook.child_environment(Path(sys.executable)), .05)

    def test_benchmark_launcher_dispatch(self):
        import run_swebench
        import run_terminal_bench
        with patch.object(notebook, "main", return_value=0) as main:
            self.assertEqual(run_swebench.main(["--backend", "notebook", "--help"]), 0)
            main.assert_called_once_with(["--help"], expected_benchmark="swebench")
        with patch.object(notebook, "main", return_value=0) as main:
            self.assertEqual(run_terminal_bench.main(["--backend", "notebook", "--help"]), 0)
            main.assert_called_once_with(["--help"], expected_benchmark="terminal-bench")

    def test_resume_missing_artifact_retries(self):
        self.assertEqual(self.invoke(), 0)
        state = json.loads((self.output / "task-01/status.json").read_text())
        (Path(state["attempt"]) / "agent-result.json").unlink()
        self.assertEqual(self.invoke("--resume"), 0)
        current = json.loads((self.output / "task-01/status.json").read_text())
        self.assertNotEqual(current["attempt"], state["attempt"])

    def test_resume_rejects_implementation_changes(self):
        self.assertEqual(self.invoke(), 0)
        with patch.object(notebook, "implementation_sha256", return_value="different-code"):
            self.assertEqual(self.invoke("--resume"), 2)

    def test_nonstring_candidate_is_reported(self):
        def bad(command, directory, env, timeout):
            atomic_write_json(directory / "agent-result.json", {"succeeded": True, "best_workspace": 42})
            return 0
        self.assertEqual(self.invoke(executor=bad), 2)

    def test_urls_cannot_persist_query_credentials(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_BASE": "https://example.org?key=secret"}):
            self.assertEqual(self.invoke("--dry-run"), 2)
        self.assertFalse(self.output.exists())

    def test_old_judge_environment_is_ignored(self):
        with patch.dict(os.environ, {"SUCCESS_JUDGE_API_BASE": "https://unused.example?key=unused", "SUCCESS_JUDGE_PROVIDER": "invalid", "SUCCESS_JUDGE_MODEL": "unused-judge"}):
            self.assertEqual(self.invoke(), 0)
        provenance = (self.output / "notebook-run.json").read_text()
        self.assertNotIn("SUCCESS_JUDGE", provenance)
        self.assertNotIn("unused-judge", provenance)
        self.assertEqual(json.loads(provenance)["success_judge_mode"], "off")

    def test_swe_patch_exports_new_files_without_changing_index(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.seed, capture_output=True, check=True).stdout
        git("init")
        git("add", ".")
        git("-c", "user.name=NotebookTest", "-c", "user.email=test@example.org", "commit", "-m", "seed")
        commit = git("rev-parse", "HEAD").decode().strip()
        index_before = (self.seed / ".git/index").read_bytes()
        (self.seed / "new.py").write_text("print('new')\n")
        (self.seed / "task.txt").write_text("modified")
        attempt = self.root / "patch-attempt"
        attempt.mkdir()
        result = notebook.export_swe_patch(self.seed, commit, attempt)
        self.assertIn("new.py", result)
        self.assertIn("modified", result)
        self.assertEqual((self.seed / ".git/index").read_bytes(), index_before)
        self.assertEqual((attempt / "model.patch").read_bytes().decode(), result)

    def prepare_swe_delivery(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.seed, capture_output=True, check=True).stdout
        git("init")
        git("config", "core.autocrlf", "false")
        git("add", ".")
        git("-c", "user.name=NotebookTest", "-c", "user.email=test@example.org", "commit", "-m", "seed")
        self.data["benchmark"] = "swebench"
        self.data["tasks"][0]["base_commit"] = git("rev-parse", "HEAD").decode().strip()
        self.write_manifest()

    def delivery_agent(self, *, status="submitted", code=0, change=True, declared_hash=None, stop_reason="submitted"):
        def agent(command, directory, env, timeout):
            candidate = directory / "snapshots" / "candidate"
            shutil.copytree(self.seed, candidate)
            if change:
                (candidate / "task.txt").write_text("candidate implementation\n")
            (candidate / ".git" / "runtime-marker").write_text("only metadata")
            artifact = inspect_git_submission(candidate, self.data["tasks"][0]["base_commit"])
            atomic_write_json(directory / "agent-result.json", {
                "succeeded": False,
                "submitted": status == "submitted",
                "stop_reason": stop_reason,
                "best_workspace": str(candidate),
                "delivery": {
                    "status": status, "has_patch": artifact.has_changes,
                    "patch_sha256": declared_hash or artifact.patch_sha256,
                    "local_validation_passed": True, "official_resolved": None,
                },
            })
            return code
        return agent

    def test_swe_delivery_exit_zero_does_not_mean_resolved(self):
        self.prepare_swe_delivery()
        self.assertEqual(self.invoke(executor=self.delivery_agent()), 0)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertEqual(state["status"], "completed")
        self.assertFalse(state["agent_succeeded"])
        self.assertTrue(state["submitted"])
        self.assertTrue(state["local_validation_passed"])
        self.assertIsNone(state["official_resolved"])
        self.assertEqual(state["patch_sha256"], state["delivery"]["patch_sha256"])
        self.assertIn("candidate implementation", json.loads((self.output / "predictions.jsonl").read_text())["model_patch"])

    def test_swe_draft_is_preserved_for_both_normal_and_unsolved_exit(self):
        self.prepare_swe_delivery()
        for code in (0, 1):
            with self.subTest(exit_code=code):
                self.output = self.root / f"draft-{code}"
                agent = self.delivery_agent(status="draft", code=code, stop_reason="budget_exhausted")
                self.assertEqual(self.invoke(executor=agent), 0)
                state = json.loads((self.output / "task-01/status.json").read_text())
                self.assertEqual(state["status"], "completed")
                self.assertFalse(state["submitted"])
                self.assertFalse(state["agent_succeeded"])
                self.assertEqual(state["delivery"]["status"], "draft")
                self.assertEqual(self.invoke("--resume", executor=lambda *args: self.fail("Draft already delivered")), 0)

    def test_swe_empty_diff_is_unsolved_even_if_metadata_changed(self):
        self.prepare_swe_delivery()
        self.assertEqual(self.invoke(executor=self.delivery_agent(status="none", code=1, change=False, stop_reason="budget_exhausted")), 0)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertFalse(state["delivery"]["has_patch"])
        self.assertFalse(state["agent_succeeded"])
        self.assertEqual(json.loads((self.output / "predictions.jsonl").read_text())["model_patch"], "")

    def test_swe_delivery_hash_mismatch_is_not_accepted(self):
        self.prepare_swe_delivery()
        self.assertEqual(self.invoke(executor=self.delivery_agent(declared_hash="0" * 64)), 2)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertEqual(state["status"], "error")
        self.assertIn("hash disagree", state["error"])
        self.assertEqual((self.output / "predictions.jsonl").read_text(), "")

    def test_swe_delivery_runtime_error_still_exports_draft(self):
        self.prepare_swe_delivery()
        self.assertEqual(self.invoke(executor=self.delivery_agent(status="draft", code=1, stop_reason="runtime_error_with_checkpoint")), 2)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["delivery"]["status"], "draft")
        self.assertIn("candidate implementation", json.loads((self.output / "predictions.jsonl").read_text())["model_patch"])

    def checkpoint_process(self, *, timeout=False, mutate=None, model_usage=None):
        real_execute = notebook.execute
        create_candidate = self.delivery_agent()
        calls = []

        def agent(command, directory, env, command_timeout):
            calls.append(directory)
            create_candidate(command, directory, env, command_timeout)
            result = json.loads((directory / "agent-result.json").read_text())
            result["stop_reason"] = "running"
            if model_usage is not None:
                result["model_usage"] = model_usage
            if mutate:
                mutate(result, directory)
            atomic_write_json(directory / "snapshots/search_checkpoint.json", result)
            script = "import sys,time; print('partial process output', flush=True); "
            script += "time.sleep(5)" if timeout else "sys.exit(2)"
            return real_execute([sys.executable, "-c", script], directory, env, .05 if timeout else 5)

        return agent, calls

    def test_real_timeout_recovers_checkpoint_patch_but_remains_error(self):
        self.prepare_swe_delivery()
        recorded_usage = {"model_calls": 3, "prompt_tokens": 123, "completion_tokens": 45}
        agent, calls = self.checkpoint_process(timeout=True, model_usage=recorded_usage)
        self.assertEqual(self.invoke(executor=agent), 2)
        self.assertEqual(len(calls), 1)
        state = json.loads((self.output / "task-01/status.json").read_text())
        attempt = Path(state["attempt"])
        result = json.loads((attempt / "agent-result.json").read_text())
        prediction = json.loads((self.output / "predictions.jsonl").read_text())
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["stop_reason"], "process_timeout")
        self.assertIn("timed out", state["error"])
        self.assertTrue(state["artifact_rescued"])
        self.assertFalse(state["agent_succeeded"])
        self.assertFalse(state["submitted"])
        self.assertEqual(state["delivery"]["status"], "draft")
        self.assertIsNone(state["official_resolved"])
        self.assertEqual(result["model_usage"], recorded_usage)
        self.assertEqual(state["model_usage"], recorded_usage)
        self.assertEqual(result["error"], state["error"])
        self.assertEqual(prediction["status"], "error")
        self.assertEqual(prediction["error"], state["error"])
        self.assertIn("candidate implementation", prediction["model_patch"])
        self.assertEqual(state["patch_sha256"], state["delivery"]["patch_sha256"])
        self.assertTrue((attempt / "agent-result.process-output.txt").is_file())
        self.assertEqual((self.seed / "task.txt").read_text(), "initial")

    def test_real_exit_two_recovers_checkpoint_without_inventing_usage(self):
        self.prepare_swe_delivery()
        agent, calls = self.checkpoint_process()
        self.assertEqual(self.invoke(executor=agent), 2)
        self.assertEqual(len(calls), 1)
        state = json.loads((self.output / "task-01/status.json").read_text())
        attempt = Path(state["attempt"])
        result = json.loads((attempt / "agent-result.json").read_text())
        self.assertEqual(state["status"], "error")
        self.assertEqual(state["exit_code"], 2)
        self.assertEqual(state["stop_reason"], "process_exit_error")
        self.assertIn("exit code 2", state["error"])
        self.assertFalse(result["succeeded"])
        self.assertFalse(result["submitted"])
        self.assertEqual(result["stop_reason"], "runtime_error_with_checkpoint")
        self.assertNotIn("model_usage", result)
        self.assertNotIn("model_usage", state)
        self.assertIn("partial process output", (attempt / "agent-result.process-output.txt").read_text())
        prediction = json.loads((self.output / "predictions.jsonl").read_text())
        self.assertEqual(prediction["status"], "error")
        self.assertIn("candidate implementation", prediction["model_patch"])

    def test_invalid_checkpoint_is_not_exported_and_keeps_process_error(self):
        self.prepare_swe_delivery()
        for case in ("seed", "other-attempt", "bad-hash", "empty", "invalid-shape"):
            with self.subTest(case=case):
                self.output = self.root / f"rejected-{case}"

                def mutate(result, directory):
                    if case == "seed":
                        result["best_workspace"] = str(self.seed)
                    elif case == "other-attempt":
                        result["best_workspace"] = str(directory.parent / "attempt-other/snapshots/candidate")
                    elif case == "bad-hash":
                        result["delivery"]["patch_sha256"] = "0" * 64
                    elif case == "empty":
                        result["delivery"]["has_patch"] = False
                    else:
                        result["delivery"] = []

                agent, calls = self.checkpoint_process(mutate=mutate)
                self.assertEqual(self.invoke(executor=agent), 2)
                self.assertEqual(len(calls), 1)
                state = json.loads((self.output / "task-01/status.json").read_text())
                attempt = Path(state["attempt"])
                self.assertEqual(state["status"], "error")
                self.assertIn("exit code 2", state["error"])
                self.assertTrue(state["checkpoint_recovery_error"])
                self.assertNotIn("artifact_rescued", state)
                self.assertFalse((attempt / "model.patch").exists())
                self.assertEqual((self.output / "predictions.jsonl").read_text(), "")
                self.assertIn("partial process output", (attempt / "agent-result.json").read_text())

    def test_swe_delivery_export_failure_is_recorded_per_task(self):
        self.prepare_swe_delivery()
        valid_agent = self.delivery_agent()
        def agent(command, directory, env, timeout):
            code = valid_agent(command, directory, env, timeout)
            (directory / "snapshots/candidate/.git/HEAD").write_text("invalid HEAD\n")
            return code
        self.assertEqual(self.invoke(executor=agent), 2)
        state = json.loads((self.output / "task-01/status.json").read_text())
        self.assertEqual(state["status"], "error")
        self.assertIn("Git submission", state["error"])

    def test_swe_resume_rechecks_exported_patch_hash(self):
        self.prepare_swe_delivery()
        agent = self.delivery_agent(status="draft", stop_reason="budget_exhausted")
        self.assertEqual(self.invoke(executor=agent), 0)
        state = json.loads((self.output / "task-01/status.json").read_text())
        (Path(state["attempt"]) / "model.patch").write_text("tampered")
        called = []
        def rerun(*args):
            called.append(True)
            return agent(*args)
        self.assertEqual(self.invoke("--resume", executor=rerun), 0)
        self.assertEqual(called, [True])

    def test_swe_batch_predictions_and_resume(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.seed, capture_output=True, check=True).stdout
        git("init")
        git("add", ".")
        git("-c", "user.name=NotebookTest", "-c", "user.email=test@example.org", "commit", "-m", "seed")
        self.data["benchmark"] = "swebench"
        self.data["tasks"][0]["base_commit"] = git("rev-parse", "HEAD").decode().strip()
        self.write_manifest()
        before = notebook.tree_digest(self.seed)
        def agent(command, directory, env, timeout):
            candidate = directory / "snapshots" / "candidate"
            shutil.copytree(self.seed, candidate)
            (candidate / "new.py").write_text("print('new')\n")
            atomic_write_json(directory / "agent-result.json", {"succeeded": True, "best_workspace": str(candidate)})
            return 0
        self.assertEqual(self.invoke(executor=agent), 0)
        row = json.loads((self.output / "predictions.jsonl").read_text())
        self.assertEqual(row["instance_id"], "task-01")
        self.assertIn("new.py", row["model_patch"])
        self.assertEqual(notebook.tree_digest(self.seed), before)
        self.assertEqual(self.invoke("--resume", executor=lambda *args: self.fail("Must skip")), 0)
        self.assertEqual(json.loads((self.output / "predictions.jsonl").read_text()), row)

    def test_runtime_error_checkpoint_is_not_completed(self):
        def agent(command, directory, env, timeout):
            atomic_write_json(directory / "agent-result.json", {"succeeded": False, "best_workspace": None, "stop_reason": "runtime_error_with_checkpoint"})
            return 1
        self.assertEqual(self.invoke(executor=agent), 2)
        self.assertEqual(json.loads((self.output / "task-01/status.json").read_text())["status"], "error")

    @unittest.skipUnless(os.name == "posix", "Linux Notebook process groups")
    def test_background_descendants_stopped(self):
        attempt = self.root / "attempt"
        attempt.mkdir()
        marker = self.root / "background-marker"
        child = f"import time; from pathlib import Path; time.sleep(.5); Path({str(marker)!r}).touch()"
        parent = f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child!r}])"
        self.assertEqual(notebook.execute([sys.executable, "-c", parent], attempt, notebook.child_environment(Path(sys.executable)), 5), 0)
        time.sleep(.8)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
