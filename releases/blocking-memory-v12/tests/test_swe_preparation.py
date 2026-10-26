import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_swe_sympy as preparation
from benchmark_splits import frozen_swebench_ids


class PreparationTests(unittest.TestCase):
    def test_selected_issue_is_not_frozen(self):
        self.assertNotIn(preparation.INSTANCE, frozen_swebench_ids())

    def test_existing_nonrepository_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / preparation.INSTANCE
            seed.mkdir()
            marker = seed / "user-data.txt"
            marker.write_text("keep")
            python = root / "python"
            python.touch()
            with self.assertRaises(ValueError):
                preparation.prepare(root, python)
            self.assertEqual(marker.read_text(), "keep")

    def test_shallow_baseline_and_public_only_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / "python"
            python.touch()
            def git(seed, *args):
                return preparation.BASE_COMMIT if args == ("rev-parse", "HEAD") else ""
            response = subprocess.CompletedProcess([], 0, stdout="offline-probe\n")
            with patch.object(preparation, "git", side_effect=git) as calls, patch.object(preparation.subprocess, "run", return_value=response):
                manifest = preparation.prepare(root / "tasks", python)
            commands = [call.args[1:] for call in calls.call_args_list]
            self.assertIn(("fetch", "--depth", "1", "--no-tags", "origin", preparation.BASE_COMMIT), commands)
            self.assertFalse(any(command[0] == "reset" for command in commands))
            task = json.loads(manifest.read_text())["tasks"][0]
            self.assertEqual(task["base_commit"], preparation.BASE_COMMIT)
            self.assertNotIn("patch", task)
            self.assertNotIn("test_patch", task)
            self.assertNotIn("FAIL_TO_PASS", task)


if __name__ == "__main__":
    unittest.main()
