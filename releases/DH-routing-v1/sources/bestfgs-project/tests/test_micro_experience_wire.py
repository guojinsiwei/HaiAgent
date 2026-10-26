"""Bounded optional micro-memory travels in existing policy responses only."""
from dataclasses import replace
import json
import unittest

from bestfgs.models import (
    CommandResult, CommandSpec, ConditionalExperience, EnvironmentSnapshot,
    ExecutionOutcome, ExperiencePremise, MacroAction, StructuredContext, TaskSpec,
)
from bestfgs.retrac_adapter import (
    RetracModelConfig, RetracPolicyAdapter, _project_action_for_prompt,
    _project_observation_sources, _project_rules_for_prompt,
)
from bestfgs.rules import TaskRule
from bestfgs.priority import NodePriorityEvidence, calculate_priority


class ScriptedClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def complete_json(self, **kwargs):
        self.prompts.append(kwargs["user_prompt"])
        if not self.responses:
            raise AssertionError("optional metadata caused an extra model request")
        return self.responses.pop(0)


def adapter(client=None, mode="conditioned"):
    config = RetracModelConfig(model_name="wire-test", base_url="http://unused.invalid/v1",
        api_key="test-only", request_attempts=1, parse_attempts=2, retry_interval_seconds=0,
        hard_timeout_process=False)
    return RetracPolicyAdapter(config, client=client or ScriptedClient([]), experience_mode=mode)


def premise(**changes):
    value = {"subject": "module.py", "predicate": "file_contains", "value": "if guard:"}
    value.update(changes)
    return value


def hint(**changes):
    value = {"operation": "repair_guard", "target_paths": ["module.py"],
        "premises": [premise()], "source_channel": "functional_validation", "source_index": 0,
        "lesson": "Hypothesis: the guard may reject a valid boundary case.",
        "next_check": "Reproduce the positive and negative boundary cases."}
    value.update(changes)
    return value


def action_payload(**changes):
    value = {"name": "review_guard", "rationale": "inspect the existing patch",
        "semantic_direction_id": "repair", "semantic_direction_label": "Repair",
        "intent": "candidate", "commands": [
            {"argv": ["git", "diff"], "description": "read cumulative diff"},
            {"argv": ["python", "-c", "print('observed')"], "description": "read state"}],
        "verification_commands": [{"argv": ["python", "check.py"], "description": "public boundary check"}]}
    value.update(changes)
    return value


def assessment_payload(**changes):
    value = {"direction_status": "exploring", "task_success": False,
             "satisfied_success_criteria": [], "feedback": "The public boundary check failed."}
    value.update(changes)
    return value


def outcome_for(action):
    parent = EnvironmentSnapshot("before", ".", "old-files", "before fixture")
    child = EnvironmentSnapshot("after", ".", "new-files", "after fixture")
    gate = CommandSpec(("internal-validation-gate",), "automatic syntax gate")
    return ExecutionOutcome(parent, child, action,
        (CommandResult(action.commands[0], 0, "diff source", "", 0),
         CommandResult(action.commands[1], 0, "observed state", "", 0)),
        validation_results=(CommandResult(gate, 0, "syntax checked", "", 0),),
        functional_validation_results=(CommandResult(action.verification_commands[0], 1,
            "negative boundary failed", "AssertionError", 0),))


class MicroExperienceWireTests(unittest.TestCase):
    def test_absent_and_empty_fields_keep_the_existing_wire_compatible(self):
        policy = adapter()
        for fields in ({}, {"experience_operation": "", "experience_targets": [], "experience_premises": []}):
            action, = policy._parse_actions({"actions": [action_payload(**fields)]}, limit=1)
            self.assertEqual((action.experience_operation, action.experience_targets, action.experience_premises), ("", (), ()))
        for fields in ({}, {"micro_experiences": []}):
            assessment = policy._parse_assessment(assessment_payload(**fields))
            self.assertEqual(assessment.micro_experiences, ())
            self.assertEqual(assessment.micro_experiences_dropped, 0)

    def test_action_metadata_round_trips_without_changing_identity(self):
        policy = adapter()
        plain, = policy._parse_actions({"actions": [action_payload()]}, limit=1)
        annotated, = policy._parse_actions({"actions": [action_payload(
            experience_operation="repair_guard", experience_targets=["module.py"],
            experience_premises=[premise()])]}, limit=1)
        self.assertEqual(plain.signature(), annotated.signature())
        self.assertEqual(plain.commands, annotated.commands)
        self.assertEqual(plain.verification_commands, annotated.verification_commands)
        self.assertEqual(annotated.experience_premises, (ExperiencePremise(**premise()),))
        projected = _project_action_for_prompt(annotated)
        self.assertEqual(projected["experience_operation"], "repair_guard")
        self.assertEqual(projected["experience_targets"], ["module.py"])
        self.assertEqual(projected["experience_premises"], [premise()])
        changed = MacroAction.create(name=plain.name, rationale=plain.rationale,
            semantic_direction_id=plain.semantic_direction_id, semantic_direction_label=plain.semantic_direction_label,
            intent=plain.intent, commands=plain.commands, verification_commands=plain.verification_commands,
            experience_operation="another_operation", experience_targets=("other.py",),
            experience_premises=(ExperiencePremise("assumption", "equals", "unverified"),))
        self.assertEqual(changed.signature(), plain.signature())
        priority_args = dict(context=StructuredContext(task_goal="repair"), evidence=NodePriorityEvidence(),
            solve_pressure=0.6, direction_failures=0, action_repeat_count=0,
            consecutive_direction_count=0, estimated_tool_calls=3, max_commands_per_action=4, waiting_rounds=0)
        self.assertEqual(calculate_priority(action=plain, **priority_args),
                         calculate_priority(action=annotated, **priority_args))

    def test_model_types_reject_invalid_predicates_paths_and_non_strings(self):
        for invalid in (premise(predicate="execute"), premise(predicate=[]), premise(subject="../module.py"),
                        premise(subject="C:/module.py"), premise(value=1), premise(subject="s" * 101),
                        premise(value="x" * 161), premise(value="")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ExperiencePremise(**invalid)
        valid = hint()
        valid["target_paths"] = tuple(valid["target_paths"])
        valid["premises"] = (ExperiencePremise(**premise()),)
        for fields in ({"source_index": True}, {"source_index": 0.0}, {"source_channel": "validation"},
                       {"lesson": 1}, {"lesson": "x" * 501}, {"next_check": "x" * 301}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                ConditionalExperience(**{**valid, **fields})
        base, = adapter()._parse_actions({"actions": [action_payload()]}, limit=1)
        with self.assertRaises(ValueError):
            MacroAction.create(name=base.name, rationale=base.rationale,
                semantic_direction_id=base.semantic_direction_id, semantic_direction_label=base.semantic_direction_label,
                commands=base.commands, experience_operation="op", experience_targets=["module.py"])

    def test_invalid_optional_action_metadata_does_not_retry_valid_actions(self):
        for fields in (
            {"experience_operation": 7}, {"experience_operation": "x" * 81},
            {"experience_operation": "repair_guard", "experience_targets": ["../outside"]},
            {"experience_operation": "repair_guard", "experience_targets": ["a"] * 5},
            {"experience_operation": "repair_guard", "experience_premises": [premise(predicate="run")]},
            {"experience_operation": "repair_guard", "experience_premises": [premise()] * 5},
            {"experience_operation": "repair_guard", "experience_premises": [premise(subject="s" * 100, value="v" * 160)] * 4},
        ):
            with self.subTest(fields=fields):
                client = ScriptedClient([{"actions": [action_payload(**fields)]}])
                actions = adapter(client).propose_actions(task=TaskSpec("task", "repair"),
                    context=StructuredContext(task_goal="repair"), rules=(), limit=1)
                self.assertEqual(len(actions), 1)
                self.assertEqual(actions[0].experience_operation, "")
                self.assertEqual(actions[0].experience_premises, ())
                self.assertEqual(len(client.prompts), 1)

    def test_bad_micro_experiences_are_dropped_per_item_and_bounded(self):
        variants = [hint(operation="x" * 81), hint(source_index=True), hint(source_index=-1),
            hint(source_channel="validation"), hint(lesson="x" * 501), hint(next_check="x" * 301),
            hint(premises=[premise(predicate="causes")]), hint(target_paths=["/outside"]),
            hint(target_paths=["a"] * 5), hint(premises=[premise()] * 5), hint(lesson={}),
            hint(premises=[premise(subject="s" * 100, value="v" * 160)] * 4)]
        for invalid in variants:
            with self.subTest(invalid=invalid):
                parsed = adapter()._parse_assessment(assessment_payload(micro_experiences=[hint(), invalid]))
                self.assertEqual(len(parsed.micro_experiences), 1)
                self.assertEqual(parsed.micro_experiences_dropped, 1)
        parsed = adapter()._parse_assessment(assessment_payload(micro_experiences=[hint()] * 7,
            micro_experiences_dropped=99999))
        self.assertEqual(len(parsed.micro_experiences), 3)
        self.assertEqual(parsed.micro_experiences_dropped, 4)
        for invalid in (None, True, {}, "not a list"):
            parsed = adapter()._parse_assessment(assessment_payload(micro_experiences=invalid))
            self.assertEqual(parsed.micro_experiences, ())
            self.assertEqual(parsed.micro_experiences_dropped, 1)

    def test_existing_bootstrap_expand_update_calls_carry_metadata_without_extra_requests(self):
        annotation = dict(experience_operation="repair_guard", experience_targets=["module.py"],
                          experience_premises=[premise()])
        client = ScriptedClient([
            {"semantic_directions": [{"direction_id": "repair", "label": "Repair"}],
             "bootstrap_action": action_payload(**annotation)},
            {"actions": [action_payload(**annotation)]},
            {"assessment": assessment_payload(micro_experiences=[
                hint(source_channel="command", source_index=1),
                hint(source_channel="automatic_validation", source_index=0),
                hint(source_channel="functional_validation", source_index=0)]), "next_context": {}},
        ])
        policy = adapter(client)
        task = TaskSpec("task", "repair")
        context = StructuredContext(task_goal=task.goal)
        plan = policy.propose_initial_plan(task=task, context=context, rules=(), limit=1)
        actions = policy.propose_actions(task=task, context=context, rules=(), limit=1)
        update = policy.update_transition(task=task, previous=context, action=actions[0], outcome=outcome_for(actions[0]))
        self.assertEqual(len(client.prompts), 3)
        self.assertEqual(plan.bootstrap_action.experience_operation, "repair_guard")
        self.assertEqual(len(update.assessment.micro_experiences), 3)
        for prompt in client.prompts:
            self.assertIn("literal file-state conditions only, never causal truth", prompt)
            self.assertIn("equals/not_equals are unverified semantic declarations", prompt)
            self.assertIn("same stable operation key", prompt)
        observed = json.loads(client.prompts[2].split("Actual result source list (exact channel/index references):\n", 1)[1])
        self.assertEqual([(row["source_channel"], row["source_index"]) for row in observed],
            [("command", 0), ("command", 1), ("automatic_validation", 0), ("functional_validation", 0)])
        self.assertIn("next_check is an advisory suggestion only", client.prompts[2])

    def test_out_of_range_sources_drop_without_retry_or_losing_transition(self):
        action, = adapter()._parse_actions({"actions": [action_payload()]}, limit=1)
        client = ScriptedClient([{"assessment": assessment_payload(micro_experiences=[
            hint(source_channel="command", source_index=2), hint(source_index=True), hint()]), "next_context": {}}])
        update = adapter(client).update_transition(task=TaskSpec("task", "repair"),
            previous=StructuredContext(task_goal="repair"), action=action, outcome=outcome_for(action))
        self.assertEqual(update.assessment.direction_status, "exploring")
        self.assertEqual(len(update.assessment.micro_experiences), 1)
        self.assertEqual(update.assessment.micro_experiences_dropped, 2)
        self.assertEqual(len(client.prompts), 1)

    def test_off_and_legacy_do_not_prompt_or_ingest_new_fields(self):
        for mode in ("off", "legacy"):
            with self.subTest(mode=mode):
                client = ScriptedClient([{"actions": [action_payload(experience_operation="private_operation",
                    experience_targets=["private.py"], experience_premises=[premise()])]},
                    {"assessment": assessment_payload(micro_experiences=[hint()]), "next_context": {}}])
                policy = adapter(client, mode)
                task = TaskSpec("task", "repair")
                context = StructuredContext(task_goal=task.goal)
                action, = policy.propose_actions(task=task, context=context, rules=(), limit=1)
                self.assertEqual(action.experience_operation, "")
                action = replace(action, experience_operation="private_operation", experience_targets=("private.py",),
                                 experience_premises=(ExperiencePremise(**premise()),))
                update = policy.update_transition(task=task, previous=context, action=action, outcome=outcome_for(action))
                self.assertEqual(update.assessment.micro_experiences, ())
                self.assertEqual(update.assessment.micro_experiences_dropped, 0)
                for prompt in client.prompts:
                    for field in ("experience_operation", "experience_targets", "experience_premises", "micro_experiences", "private_operation"):
                        self.assertNotIn(field, prompt)

    def test_source_projection_keeps_indices_and_marks_shortened_observations(self):
        action, = adapter()._parse_actions({"actions": [action_payload()]}, limit=1)
        outcome = outcome_for(action)
        outcome = replace(outcome, command_results=(replace(outcome.command_results[0],
            stdout="x" * 10000, output_truncated=True), outcome.command_results[1]))
        sources, counts = _project_observation_sources(outcome, 1800)
        self.assertEqual(counts, {"command": 2, "automatic_validation": 1, "functional_validation": 1})
        self.assertEqual(len(sources), 4)
        self.assertTrue(sources[0]["output_truncated"])
        self.assertTrue(sources[0]["display_truncated"])

    def test_rule_projection_preserves_whole_literal_premises_and_source_status(self):
        condition = {**premise(), "status": "satisfied", "observed": "large output" * 500, "reason": "long reason" * 500}
        rule = TaskRule("rule-micro", "task", "avoid", "repair", "repair_guard",
            evidence=("actual source return_code=1; assertion failed",), condition="if the literal guard remains",
            guidance="Hypothesis to verify", evidence_ids=("source-1", "source-2", "source-3"),
            micro_experience_id="micro-1", source_count=9, operation="repair_guard", target_paths=("module.py",),
            premises=(condition,), match_reasons=("operation and target match",), source_validity="mixed")
        item, = _project_rules_for_prompt((rule,))
        self.assertLessEqual(len(json.dumps([item], ensure_ascii=False, separators=(",", ":"))), 2500)
        self.assertEqual(item["premises"], [{**premise(), "status": "satisfied"}])
        self.assertEqual(item["source_validity"], "mixed")
        self.assertEqual(item["source_count"], 9)
        self.assertEqual(item["evidence_ids"], ["source-1", "source-2", "source-3"])
        self.assertEqual(item["operation"], "repair_guard")
        self.assertEqual(item["target_paths"], ["module.py"])
        self.assertTrue(item["match_reasons"])
        oversized = replace(rule, target_paths=("x" * 5000,))
        self.assertEqual(_project_rules_for_prompt((oversized,)), [])


if __name__ == "__main__":
    unittest.main()
