"""Offline integration tests: the blocker may steer tools, not fabricate evidence."""
from __future__ import annotations

import json
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from bestfgs.environment import ForkedWorkspaceEnvironment
from bestfgs.evidence_runtime import run_evidence
from bestfgs.experiment_metrics import ExperimentRecorder
from bestfgs.models import TaskSpec, ModelCallError
from bestfgs.retrac_adapter import RetracModelConfig


def command(code):
    return {"argv": [sys.executable, "-c", code], "description": "public task operation"}


def run_script():
    return {"done": False, "commands": [{"argv": [sys.executable, "missing_task.py"],
                                         "description": "run public task script"}]}


def repair_script():
    return {"done": False, "commands": [command(
        "from pathlib import Path; Path('missing_task.py').write_text('print(42)\\n', encoding='utf-8')")]}


def submission():
    return {"done": True, "commands": [command("print('review current draft')")],
            "verification_commands": [command("assert True")]}


class FakeClient:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.prompts = []

    def complete_json(self, **kwargs):
        self.prompts.append(kwargs)
        try:
            payload = next(self.payloads)
        except StopIteration as error:
            raise ModelCallError("fixture exhausted") from error
        payload = payload(json.loads(kwargs["user_prompt"])) if callable(payload) else payload
        return submission() if payload == {"done": True} else payload

    def usage_summary(self):
        return {"model_calls": len(self.prompts), "api_requests": len(self.prompts)}


class BlockingRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.seed = self.root / "seed"
        self.seed.mkdir()
        (self.seed / "original.txt").write_text("preserve me\n", encoding="utf-8")
        self.config = RetracModelConfig(api_key="test-only", model_name="offline-fake",
            base_url="https://example.invalid", max_commands_per_action=4, parse_attempts=2)
        self.sequence = 0

    def run_agent(self, payloads, *, mode="control", tools=20, turns=12, memory=False,
                  branching=False, environment_type=ForkedWorkspaceEnvironment):
        self.sequence += 1
        root = self.root / f"run-{self.sequence}"
        recorder = ExperimentRecorder(root / "cli-metrics.jsonl")
        environment = environment_type(self.seed, root, recorder=recorder)
        client = FakeClient(payloads)
        result = run_evidence(TaskSpec.create("Create and run the public task script"),
            environment, client, self.config, max_iterations=turns, max_tool_calls=tools,
            max_commands=4, memory_enabled=memory, branching_enabled=branching,
            blocking_memory_mode=mode)
        trace = json.loads((root / "evidence-trace.json").read_text(encoding="utf-8"))
        return result, client, trace

    def test_missing_script_probed_deferred_repaired_and_resumed(self):
        result, client, trace = self.run_agent([
            run_script(), run_script(), run_script(), repair_script(), run_script(), {"done": True}])
        self.assertEqual(result["stop_reason"], "submitted")
        self.assertEqual(result["decision_turns"], 6)
        self.assertEqual(result["model_usage"]["model_calls"], 6)
        self.assertEqual(result["total_tool_calls"], 6)
        self.assertEqual(result["interaction_rounds"], 5)
        self.assertEqual(result["comparison_metrics"]["tool_calls"], 6)
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 1)
        self.assertEqual((Path(result["best_workspace"]) / "missing_task.py").read_text(), "print(42)\n")
        self.assertFalse((self.seed / "missing_task.py").exists())
        self.assertFalse(result["succeeded"])
        self.assertIsNone(result["official_resolved"])
        self.assertEqual(len(trace["decisions"]), 6)
        self.assertIn("42", json.loads(client.prompts[-1]["user_prompt"])["transcript"][-1]["content"])
        self.assertGreaterEqual(result["blocking_memory_metrics"]["records_created"], 1)

    def test_off_and_advisory_modes_do_not_insert_or_defer_tools(self):
        for mode in ("off", "advisory"):
            with self.subTest(mode=mode):
                result, _, _ = self.run_agent([
                    run_script(), run_script(), run_script(), repair_script(), run_script(), {"done": True}],
                    mode=mode)
                self.assertEqual(result["total_tool_calls"], 7)
                self.assertEqual(result["interaction_rounds"], 6)
                self.assertEqual(result["probe_tool_calls"], 0)
                self.assertEqual(result["deferred_action_batches"], 0)
                self.assertEqual(result["decision_turns"], 6)

    def test_probe_spends_shared_tool_budget_without_running_original_batch(self):
        result, client, _ = self.run_agent([run_script(), run_script()], tools=2)
        self.assertEqual(result["stop_reason"], "tool_budget")
        self.assertEqual(result["total_tool_calls"], 2)
        self.assertEqual(result["comparison_metrics"]["tool_calls"], 2)
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["decision_turns"], 2)
        self.assertEqual(len(client.prompts), 2)

    def test_probe_replaces_whole_batch_so_later_effects_do_not_run(self):
        retry = run_script()
        retry["commands"].append(command("from pathlib import Path; Path('must_not_exist').write_text('bad')"))
        result, _, _ = self.run_agent([run_script(), retry, {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["total_tool_calls"], 4)
        self.assertFalse((Path(result["best_workspace"]) / "must_not_exist").exists())

    def test_generic_assertion_failures_are_not_inferred_as_preconditions(self):
        failure = {"done": False, "commands": [command("raise AssertionError('incorrect algorithm')")]}
        result, _, _ = self.run_agent([failure, failure, failure, {"done": True}])
        self.assertEqual(result["total_tool_calls"], 5)
        self.assertEqual(result["probe_tool_calls"], 0)
        self.assertEqual(result["deferred_action_batches"], 0)

    def test_write_before_known_bad_command_is_not_prejudged(self):
        batch = repair_script()
        batch["commands"].extend(run_script()["commands"])
        result, client, _ = self.run_agent([run_script(), run_script(), batch, {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 0)
        self.assertEqual(result["total_tool_calls"], 6)
        self.assertIn("42", json.loads(client.prompts[-1]["user_prompt"])["transcript"][-1]["content"])

    def test_confirmed_block_has_bounded_lease_not_permanent_blacklist(self):
        result, _, _ = self.run_agent([
            run_script(), run_script(), run_script(), run_script(), {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 1)
        self.assertEqual(result["total_tool_calls"], 5)
        self.assertEqual(result["decision_turns"], 6)

    def test_restored_snapshot_does_not_inherit_confirmed_block(self):
        def restore_root(prompt):
            return {"done": False, "restore_snapshot": prompt["available_snapshots"][0]["id"],
                    "branch_reason": "Retry from the original branch"}
        result, _, _ = self.run_agent([
            run_script(), run_script(), restore_root, run_script(), {"done": True}], branching=True)
        self.assertEqual(result["snapshot_restores"], 1)
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 0)
        self.assertEqual(result["total_tool_calls"], 5)

    def test_repair_before_verification_is_not_prejudged(self):
        check = {"done": False, "verification_commands": run_script()["commands"]}
        batch = repair_script()
        batch["verification_commands"] = run_script()["commands"]
        result, _, _ = self.run_agent([check, check, batch, {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 0)
        self.assertEqual(result["total_tool_calls"], 6)
        self.assertTrue(result["local_validation_passed"])

    def test_malformed_override_is_schema_error_not_permission_to_bypass(self):
        bad = run_script()
        bad["retry_blocker"] = {"id": "some-id", "reason": ""}
        result, _, _ = self.run_agent([bad, {"done": True}])
        self.assertEqual(result["decision_turns"], 2)
        self.assertEqual(result["model_usage"]["model_calls"], 3)
        self.assertEqual(result["total_tool_calls"], 2)

    def test_explicit_override_releases_advertised_blocker_and_executes_retry(self):
        def override(prompt):
            records = [json.loads(line) for line in prompt["blocking_memory"].splitlines()
                       if line.startswith("{")]
            confirmed = next(record for record in records if record["state"] == "confirmed_blocked")
            payload = run_script()
            payload["retry_blocker"] = {"id": confirmed["blocker_id"],
                "reason": "Run the exact command to obtain a fresh public failure observation."}
            return payload
        result, _, trace = self.run_agent([run_script(), run_script(), override, {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 0)
        self.assertEqual(result["total_tool_calls"], 5)
        self.assertEqual(result["blocking_memory_metrics"]["override_releases"], 1)
        self.assertIn("retry_blocker", trace["decisions"][2])
        self.assertEqual(trace["decisions"][2]["executed_tool_calls"], 1)

    def test_unknown_id_cannot_authorize_blocker_override(self):
        payload = run_script()
        payload["retry_blocker"] = {"id": "not-from-this-task", "reason": "attempted bypass"}
        result, _, _ = self.run_agent([payload, {"done": True}])
        self.assertEqual(result["decision_turns"], 2)
        self.assertEqual(result["model_usage"]["model_calls"], 3)
        self.assertEqual(result["blocking_memory_metrics"]["override_releases"], 0)
        self.assertEqual(result["total_tool_calls"], 2)

    def test_unknown_or_failed_diagnostic_never_grants_a_block(self):
        for failed in (False, True):
            class InconclusiveProbeEnvironment(ForkedWorkspaceEnvironment):
                def verify(self, snapshot, commands):
                    results = super().verify(snapshot, commands)
                    if any(command.description.startswith("Read-only blocking-condition diagnostic")
                           for command in commands):
                        return tuple(replace(result, return_code=1 if failed else 0,
                                             stdout="unrecognized diagnostic output\n",
                                             stderr="diagnostic failed" if failed else "")
                                     for result in results)
                    return results
            with self.subTest(failed=failed):
                result, _, trace = self.run_agent([
                    run_script(), run_script(), run_script(), {"done": True}],
                    environment_type=InconclusiveProbeEnvironment)
                self.assertEqual(result["probe_tool_calls"], 1)
                self.assertEqual(result["deferred_action_batches"], 0)
                self.assertEqual(result["total_tool_calls"], 5)
                self.assertEqual(result["comparison_metrics"]["tool_calls"], 5)
                self.assertEqual(result["blocking_memory_metrics"]["probes_unknown"], 1)
                self.assertEqual(trace["decisions"][2]["kind"], "action")

    def test_successful_diagnostic_does_not_count_as_passing_task_verification(self):
        check = {"done": False, "verification_commands": run_script()["commands"]}
        result, _, trace = self.run_agent([check, check, {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["total_tool_calls"], 4)
        self.assertFalse(result["local_validation_passed"])
        self.assertFalse(result["verified_success"])
        self.assertEqual(result["explicit_check_count"], 2)
        self.assertEqual(result["unresolved_or_stale_check_count"], 1)
        self.assertEqual(len(trace["checks"]), 2)
        self.assertFalse(trace["checks"][0]["passed"])
        self.assertTrue(trace["checks"][1]["passed"])
        self.assertEqual(trace["decisions"][1]["kind"], "blocker_probe")
        self.assertIn("diagnostic_command", trace["decisions"][1])

    def test_probe_cap_never_blocks_execution_after_diagnostics_are_exhausted(self):
        with patch("bestfgs.evidence_runtime.MAX_BLOCKER_PROBES", 1):
            result, _, trace = self.run_agent([
                run_script(), run_script(), run_script(), run_script(), {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 0)
        self.assertEqual(result["total_tool_calls"], 6)
        self.assertTrue(trace["decisions"][2]["blocker_probe_budget_exhausted"])
        self.assertTrue(trace["decisions"][3]["blocker_probe_budget_exhausted"])

    def test_changed_environment_invalidates_confirmed_condition(self):
        def change_environment(_prompt):
            os.environ["BESTFGS_V12_TEST_STATE"] = "after"
            return run_script()
        with patch.dict(os.environ, {"BESTFGS_V12_TEST_STATE": "before"}):
            result, _, trace = self.run_agent([
                run_script(), run_script(), change_environment, {"done": True}])
        self.assertEqual(result["probe_tool_calls"], 1)
        self.assertEqual(result["deferred_action_batches"], 0)
        self.assertEqual(result["total_tool_calls"], 5)
        self.assertEqual(trace["decisions"][2]["kind"], "action")
        self.assertGreaterEqual(result["blocking_memory_metrics"]["invalidated_records"], 1)


if __name__ == "__main__":
    unittest.main()
