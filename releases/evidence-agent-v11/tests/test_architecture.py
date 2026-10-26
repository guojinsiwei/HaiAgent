import unittest
from pathlib import Path

import bestfgs
from bestfgs.agent import TaskRunner
from bestfgs.best_first import SemanticBestFirstGraphSearch
from bestfgs.best_first_runtime import BestFGSConfig, BestFirstSearchRuntime


class BestFGSArchitectureTests(unittest.TestCase):
    def test_default_search_owns_its_runtime(self) -> None:
        self.assertTrue(issubclass(SemanticBestFirstGraphSearch, BestFirstSearchRuntime))
        self.assertIsInstance(TaskRunner(object(), object()).config, BestFGSConfig)

    def test_package_contains_only_best_fgs_modules(self) -> None:
        package_dir = Path(bestfgs.__file__).parent
        modules = {path.name for path in package_dir.glob("*.py")}
        self.assertEqual(
            modules,
            {
                "__init__.py", "__main__.py", "agent.py", "best_first.py",
                "best_first_runtime.py", "environment.py", "metrics.py", "models.py",
                "priority.py", "retrac_adapter.py", "model_wire.py", "rl.py", "rules.py", "semantic.py",
                "success_judge.py", "submission.py", "experience.py", "micro_experience.py",
                "raw_baseline.py", "cli_config.py", "experiment_metrics.py", "redundancy.py",
                "evidence_runtime.py", "evidence_memory.py",
            },
        )

    def test_best_fgs_config_exposes_native_frontier_settings(self) -> None:
        config = BestFGSConfig()
        self.assertGreaterEqual(config.max_children_per_node, config.base_children_per_node)
        self.assertGreater(config.frontier_max_entries_per_direction, 0)


if __name__ == "__main__":
    unittest.main()
