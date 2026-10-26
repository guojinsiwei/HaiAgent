from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import run_comparison as comparison
from bestfgs import __main__ as cli
from bestfgs.agent import TaskRunner


class V13BranchingRestoreTests(unittest.TestCase):
    def test_cli_defaults_to_graph_search(self):
        args = cli.build_parser().parse_args(["--goal", "repair", "--workspace", "."])
        self.assertEqual(args.engine, "graph")
        self.assertEqual(args.blocking_memory, "off")

    def test_paired_protocol_keeps_raw_sequential_and_bestfgs_graph(self):
        bestfgs = comparison.ARM_CONFIGURATIONS["bestfgs"]
        raw = comparison.ARM_CONFIGURATIONS["raw"]
        self.assertEqual(bestfgs["algorithm"], "phase_adaptive_semantic_best_first")
        self.assertEqual(bestfgs["engine"], "graph")
        self.assertIs(bestfgs["branching_enabled"], True)
        self.assertEqual(raw["algorithm"], "raw_cli")
        self.assertEqual(raw["engine"], "evidence")
        self.assertIs(raw["branching_enabled"], False)
        self.assertIn("--disable-evidence-branching", comparison.method_args("raw"))
        self.assertNotIn("--disable-evidence-branching", comparison.method_args("bestfgs"))

    def test_graph_bootstrap_instruction_preserves_alternatives(self):
        source = Path(TaskRunner.__module__.replace(".", "/"))
        del source  # The assertion below deliberately checks behavior via source text.
        text = (ROOT / "src/bestfgs/agent.py").read_text(encoding="utf-8")
        self.assertIn("preserve viable", text)
        self.assertIn("global evidence-ranked", text)


if __name__ == "__main__":
    unittest.main()
