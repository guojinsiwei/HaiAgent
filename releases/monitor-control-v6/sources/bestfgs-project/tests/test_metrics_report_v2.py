import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import audit_tool_repetition as audit
import compare_experiments as comparison
import test_raw_comparison as fixtures
from bestfgs.experiment_metrics import METRIC_VERSION, METRIC_REPORT_VERSION, summarize_trace


class MetricReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "old-trace.jsonl"
        events = [{"event": "header", "metric_version": "cli-comparison-v1"},
                  {"event": "round_start", "round_id": 1, "phase": "action"},
                  {"event": "round_start", "round_id": 2, "phase": "final_verification"}]
        for identity, phase, repeat in ((1, "action", False), (2, "functional_verification", True),
                                         (3, "final_verification", False)):
            events.append({"event": "tool_start", "call_id": identity, "round_id": 1 if identity < 3 else 2,
                           "phase": phase, "command_sha256": "a" if identity < 3 else "b", "before_sha256": "s"})
            events.append({"event": "tool_end", "call_id": identity, "redundant": repeat,
                           "after_sha256": "s", "observation_sha256": "x" if identity < 3 else "y",
                           "blocked": False, "timed_out": False, "instrumentation_seconds": 0})
        self.events = events
        self.save()

    def save(self):
        self.path.write_text("\n".join(json.dumps(e) for e in self.events) + "\n", encoding="utf-8")

    def reviewed(self):
        packet = audit.prepare_audit(self.path, sample_size=30)
        for row in packet["items"]:
            row.update(label="other_nonredundant", reviewer="reviewer-1", rationale="Fixture contextual review",
                       evidence_refs=[f"fixture-log:call-{row['call_id']}"])
        return packet

    def test_trace_arithmetic_and_rounds_unchanged_alias_is_explicit(self):
        original = self.path.read_bytes()
        result = summarize_trace(self.path)
        self.assertEqual(result["interaction_rounds"], 2)
        self.assertEqual(result["metric_version"], "cli-comparison-v1")
        self.assertEqual(result["metric_report_version"], METRIC_REPORT_VERSION)
        self.assertEqual(result["mechanical_repeat_rate"], 1 / 3)
        self.assertEqual(result["mechanical_repeat_by_phase"]["functional_verification"]["mechanical_repeat_rate"], 1)
        self.assertIsNone(result["avoidable_repeat_rate"])
        self.assertEqual(self.path.read_bytes(), original)

    def test_incomplete_trace_is_unknown_not_zero(self):
        self.events.pop()
        self.save()
        self.assertIsNone(summarize_trace(self.path)["mechanical_repeat_rate"])
        with self.assertRaises(ValueError):
            audit.prepare_audit(self.path)

    def test_no_calls_has_no_rate(self):
        self.events = self.events[:1]
        self.save()
        self.assertIsNone(summarize_trace(self.path)["mechanical_repeat_rate"])
        report = audit.summarize_audit(self.path, audit.prepare_audit(self.path))
        self.assertIsNone(report["avoidable_repeat_rate_in_sample"])
        self.assertIsNone(report["sample_rate_bounds_due_to_unknowns"])

    def test_sample_includes_detector_negative_calls_is_fixed_and_unlabelled(self):
        packet = audit.prepare_audit(self.path)
        self.assertEqual(packet, audit.prepare_audit(self.path))
        self.assertEqual([row["call_id"] for row in packet["items"]], [1, 2, 3])
        self.assertTrue(all(row["label"] is None for row in packet["items"]))
        result = audit.summarize_audit(self.path, packet)
        self.assertIsNone(result["avoidable_repeat_rate_in_sample"])
        self.assertEqual(result["sample_rate_bounds_due_to_unknowns"], [0, 1])

    def test_necessary_repeat_not_counted_as_avoidable_by_audit(self):
        packet = self.reviewed()
        packet["items"][1]["label"] = "necessary_reverification"
        result = audit.summarize_audit(self.path, packet)
        self.assertEqual(result["whole_trace_avoidable_repeat_rate"], 0)
        self.assertEqual(result["mechanical_repeat_label_counts"], {"necessary_reverification": 1})
        self.assertEqual(summarize_trace(self.path)["mechanical_repeat_rate"], 1 / 3)

    def test_different_command_can_be_contextually_avoidable(self):
        packet = self.reviewed()
        packet["items"][2].update(label="avoidable_repeat", earlier_call_ids=[1])
        result = audit.summarize_audit(self.path, packet)
        self.assertEqual(result["avoidable_repeat_rate_in_sample"], 1 / 3)
        self.assertIsNone(result["causal_tool_calls_saved"])

    def test_uncertain_stays_in_denominator_and_is_not_a_ci(self):
        packet = self.reviewed()
        packet["items"][1].update(label="uncertain", evidence_refs=[])
        result = audit.summarize_audit(self.path, packet)
        self.assertIsNone(result["avoidable_repeat_rate_in_sample"])
        self.assertEqual(result["sample_rate_bounds_due_to_unknowns"], [0, 1 / 3])
        self.assertFalse(result["bounds_are_confidence_intervals"])

    def test_partial_sample_not_reported_as_whole_run_rate(self):
        packet = audit.prepare_audit(self.path, sample_size=1)
        for row in packet["items"]:
            row.update(label="other_nonredundant", reviewer="r", rationale="context", evidence_refs=["log"])
        result = audit.summarize_audit(self.path, packet)
        self.assertEqual(result["avoidable_repeat_rate_in_sample"], 0)
        self.assertIsNone(result["whole_trace_avoidable_repeat_rate"])

    def test_source_and_sample_tampering_rejected(self):
        for mutation in (lambda p: p["items"].pop(),
                         lambda p: p["items"][0].update(call_id=99),
                         lambda p: p["protocol"]["rubric"].update(avoidable_repeat="anything")):
            packet = self.reviewed()
            mutation(packet)
            with self.assertRaises(ValueError):
                audit.summarize_audit(self.path, packet)
        packet = self.reviewed()
        self.events[-1]["observation_sha256"] = "modified"
        self.save()
        with self.assertRaises(ValueError):
            audit.summarize_audit(self.path, packet)

    def test_labels_require_context_and_real_earlier_call(self):
        for change in ({"label": "avoidable_repeat", "earlier_call_ids": []},
                       {"label": "avoidable_repeat", "earlier_call_ids": [99]},
                       {"label": "avoidable_repeat", "earlier_call_ids": [True]},
                       {"label": "necessary_reverification", "evidence_refs": []},
                       {"label": "other_nonredundant", "rationale": ""}):
            packet = self.reviewed()
            packet["items"][1].update(change)
            with self.assertRaises(ValueError):
                audit.summarize_audit(self.path, packet)

    def test_duplicate_trace_events_rejected_for_audit(self):
        self.events.extend(copy.deepcopy(self.events[2:4]))
        self.save()
        with self.assertRaises(ValueError):
            audit.prepare_audit(self.path)

    def test_report_cli_omits_deprecated_labels_never_overwrites(self):
        output = self.root / "report.json"
        with redirect_stdout(io.StringIO()):
            audit.main(["report", "--trace", str(self.path), "--output", str(output)])
        data = json.loads(output.read_text(encoding="utf-8"))
        self.assertNotIn("tool_call_redundancy_rate", data)
        before = output.read_bytes()
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            audit.main(["report", "--trace", str(self.path), "--output", str(output)])
        self.assertEqual(output.read_bytes(), before)

    def test_comparison_preserves_success_rounds_but_does_not_certify_redundancy(self):
        a, b = fixtures.evaluated("bestfgs"), fixtures.evaluated("raw")
        for data in (a, b):
            for task in data['tasks']:
                task['comparison_metrics'].pop('redundancy_version', None)
        result = comparison.compare(a, b, repeats=200)
        self.assertEqual(result["success"]["bestfgs"]["rate"], .5)
        self.assertEqual(result["efficiency_cohorts"]["all_complete_single_attempt_pairs"]["bestfgs"]["mean_interaction_rounds"], 3)
        self.assertIsNone(result["targets"]["confirmed_reusable_call_rate_minus_50_percent_on_joint_success"]["point_estimate_meets_target"])
        self.assertEqual(result["metric_report_version"], METRIC_REPORT_VERSION)
        rates = result["efficiency_cohorts"]["all_complete_single_attempt_pairs"]["bestfgs"]
        self.assertIsNone(rates["confirmed_reusable_call_rate"])
        self.assertIsNone(rates["mechanical_repeat_by_phase"])


if __name__ == "__main__":
    unittest.main()
