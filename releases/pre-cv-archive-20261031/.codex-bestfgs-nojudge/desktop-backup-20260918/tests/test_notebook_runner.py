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
