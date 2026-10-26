"""Offline fixtures only: no Docker, tb executable, network or model calls."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from recuris.evolution import Candidate
from recuris.memory import load_memory, memory_digest
from recuris.tta import AttemptError, LONGCLI_COMMIT, TTAConfig, build_command, read_attempt, run_tta


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def config(tmp_path):
    bench = tmp_path / "longcli"
    task = bench / "tasks_long_cli" / "demo_task" / "task.yaml"
    task.parent.mkdir(parents=True)
    task.write_text("instruction: Public task\n", encoding="utf-8")
    return TTAConfig(bench, "demo_task", "provider/model", tmp_path / "campaign",
                     agent_kwargs={"api_key_env": "OPENAI_API_KEY"})


class FakeHarness:
    def __init__(self, outcomes=(False, True), *, mode="normal"):
        self.outcomes = iter(outcomes)
        self.mode = mode
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[0] == "git":
            return SimpleNamespace(returncode=0, stdout=LONGCLI_COMMIT + "\n", stderr="")
        if self.mode == "process_error":
            return SimpleNamespace(returncode=1, stdout="private verifier text", stderr="")
        args = dict(zip(argv[2::2], argv[3::2]))
        run_id = args["--run-id"]
        task = args["--task-id"]
        trial = f"{task}.1-of-1.{run_id}"
        td = Path(args["--output-path"]) / run_id / task / trial
        memory_arg = next(argv[i + 1] for i, x in enumerate(argv) if x == "--agent-kwarg" and argv[i + 1].startswith("memory_path="))
        memory = load_memory(memory_arg.split("=", 1)[1])
        result = {"trial_name": trial, "task_id": task, "is_resolved": next(self.outcomes),
                  "failure_mode": "unset", "test_started_at": "start", "test_ended_at": "end",
                  "trial_ended_at": "end", "long_cli_test_turns": [{"hidden_checker": "PRIVATE"}],
                  "instruction": "must never send official envelope to meta"}
        if self.mode == "null":
            result["is_resolved"] = None
        elif self.mode == "test_timeout":
            result["failure_mode"] = "test_timeout"
        elif self.mode == "agent_timeout":
            result["failure_mode"] = "agent_timeout"
        elif self.mode == "no_test":
            result["test_ended_at"] = None
        elif self.mode == "wrong_task":
            result["task_id"] = "other"
        elif self.mode == "two_rounds":
            result["long_cli_test_turns"] *= 2
        if self.mode != "missing":
            write(td / "results.json", result)
        actor = td / "agent-logs" / "recuris" / "one"
        write(actor / "context.json", {"instruction": "Public task", "memory_digest": memory_digest(memory)})
        trace = [{"step_id": 1, "action": {"keystrokes": "ls\n"}, "observation": "visible output"}]
        if self.mode == "leaky_trace":
            trace[0]["verifier_result"] = "PRIVATE"
        write(actor / "trace.json", trace)
        write(actor / "result.json", {"error": None, "input_tokens": 11, "output_tokens": 3, "model_calls": 2})
        if self.mode == "two_actors":
            write(actor.parent / "two" / "context.json", {"instruction": "unexpected"})
        return SimpleNamespace(returncode=0, stdout="private verifier console", stderr="")


class Meta:
    def __init__(self, noop=False):
        self.calls = []
        self.noop = noop

    def propose(self, memory, instruction, trace, mode):
        self.calls.append((deepcopy(memory), instruction, deepcopy(trace), mode))
        new = deepcopy(memory)
        if not self.noop:
            new["E"].append({"id": "verify", "description": "check outputs", "content": "Read validation.", "tags": []})
        return Candidate([], memory_digest(memory), new, [] if self.noop else ["E"],
                         memory_digest(new), mode, no_op=self.noop)


def test_adaptation_learns_only_after_official_failure(config):
    harness, meta = FakeHarness(), Meta()
    summary = run_tta(config, meta, runner=harness)
    assert summary["status"] == "succeeded"
    assert summary["attempts_used"] == 2
    assert summary["passed_at_attempt"] == 2
    assert len(meta.calls) == 1
    _, instruction, trace, mode = meta.calls[0]
    assert instruction == "Public task" and mode == "tta"
    assert "PRIVATE" not in json.dumps(trace)
    assert "private verifier console" not in json.dumps(meta.calls)
    assert summary["attempts"][0]["memory_digest"] != summary["attempts"][1]["memory_digest"]
    commands = [argv for argv, _ in harness.calls if argv[0] != "git"]
    assert commands[0][commands[0].index("--run-id") + 1] != commands[1][commands[1].index("--run-id") + 1]
    assert all(cmd[cmd.index("--n-attempts") + 1] == "1" for cmd in commands)
    assert all(cmd[cmd.index("--give-test-output") + 1] == "1" for cmd in commands)


def test_frozen_uses_same_memory_and_no_meta(config):
    cfg = replace(config, mode="frozen", attempts=2)
    meta = Meta()
    summary = run_tta(cfg, meta, runner=FakeHarness((False, False)))
    assert summary["status"] == "exhausted" and summary["official_success"] is False
    assert not meta.calls
    assert len({x["memory_digest"] for x in summary["attempts"]}) == 1


@pytest.mark.parametrize("mode", ["missing", "null", "test_timeout", "no_test", "wrong_task", "two_rounds", "process_error", "leaky_trace", "two_actors"])
def test_incomplete_outcomes_are_not_failures(config, mode):
    meta = Meta()
    summary = run_tta(config, meta, runner=FakeHarness((False,), mode=mode))
    assert summary["status"] == "incomplete"
    assert summary["official_success"] is None
    assert not meta.calls
    assert summary["attempts_used"] == 0


def test_agent_timeout_with_completed_verifier_is_an_outcome(config):
    summary = run_tta(replace(config, attempts=1), runner=FakeHarness((False,), mode="agent_timeout"))
    assert summary["status"] == "exhausted"
    assert summary["official_success"] is False


def test_success_does_not_request_meta(config):
    meta = Meta()
    summary = run_tta(config, meta, runner=FakeHarness((True,)))
    assert summary["status"] == "succeeded" and len(summary["attempts"]) == 1
    assert not meta.calls


def test_noop_keeps_memory(config):
    summary = run_tta(replace(config, attempts=2), Meta(noop=True), runner=FakeHarness((False, False)))
    assert summary["status"] == "exhausted"
    assert summary["attempts"][0]["meta_no_op"] is True
    assert summary["attempts"][0]["memory_digest"] == summary["attempts"][1]["memory_digest"]


def test_shared_first_attempt_is_read_only_and_provenance_checked(config):
    first = run_tta(replace(config, mode="frozen", attempts=1), runner=FakeHarness((False,)))
    seed = Path(first["attempts"][0]["attempt_dir"])
    before = {p.relative_to(seed): p.read_bytes() for p in seed.rglob("*") if p.is_file()}
    cfg = replace(config, output_dir=config.output_dir.parent / "paired", attempts=2, seed_attempt_dir=seed)
    harness, meta = FakeHarness((True,)), Meta()
    result = run_tta(cfg, meta, runner=harness)
    assert result["status"] == "succeeded" and result["attempts"][0]["reused"]
    assert len([c for c, _ in harness.calls if c[0] != "git"]) == 1
    assert before == {p.relative_to(seed): p.read_bytes() for p in seed.rglob("*") if p.is_file()}
    wrong = replace(cfg, model_name="different/model", output_dir=config.output_dir.parent / "wrong")
    result = run_tta(wrong, Meta(), runner=FakeHarness(()))
    assert result["status"] == "incomplete" and "provenance" in result["error"]


def test_read_attempt_has_restricted_evidence_and_detects_modified_bytes(config):
    summary = run_tta(replace(config, attempts=1), runner=FakeHarness((False,)))
    root = Path(summary["attempts"][0]["attempt_dir"])
    evidence = read_attempt(root)
    assert evidence["success"] is False
    assert "PRIVATE" not in json.dumps(evidence)
    receipt = json.loads((root / "attempt.json").read_text())
    (root / receipt["artifacts"]["trace"]["path"]).write_text("[]", encoding="utf-8")
    with pytest.raises(AttemptError, match="hash mismatch"):
        read_attempt(root)


def test_no_overwrite_existing_run(config):
    config.output_dir.mkdir()
    with pytest.raises(FileExistsError):
        run_tta(replace(config, attempts=1), runner=FakeHarness((True,)))


@pytest.mark.parametrize("changes", [
    {"attempts": 0}, {"attempts": 5}, {"attempts": True}, {"task_id": "../bad"},
    {"agent_kwargs": {"api_key": "do-not-save"}}, {"agent_kwargs": {"base_url": "http://x?a=b"}},
    {"agent_kwargs": {"base_url": "https://user:placeholder@host/v1"}},
    {"agent_kwargs": {"api_key_env": "invalid-name"}},
    {"agent_kwargs": {"extra_body": {"nested": {"access_token": "placeholder"}}}},
    {"agent_kwargs": {"memory_path": "other"}}, {"process_timeout_seconds": 1},
])
def test_invalid_configuration_rejected_before_run(config, changes):
    harness = FakeHarness(())
    with pytest.raises(ValueError):
        run_tta(replace(config, **changes), Meta(), runner=harness)
    assert not harness.calls


def test_wrong_checkout_rejected(config):
    def runner(argv, **kwargs):
        return SimpleNamespace(returncode=0, stdout="not-the-pin", stderr="")
    with pytest.raises(AttemptError, match="checked out"):
        run_tta(replace(config, attempts=1), runner=runner)
    assert not config.output_dir.exists()


def test_tta_rejects_non_experiential_edit(config):
    class WrongMeta(Meta):
        def propose(self, memory, instruction, trace, mode):
            candidate = super().propose(memory, instruction, trace, mode)
            candidate.candidate_memory["W"]["max_goals"] = 7
            candidate.candidate_digest = memory_digest(candidate.candidate_memory)
            return candidate
    summary = run_tta(config, WrongMeta(), runner=FakeHarness((False,)))
    assert summary["status"] == "incomplete"
    assert summary["attempts_used"] == 1
    assert "non-E" in summary["error"]


def test_process_timeout_does_not_diagnose(config):
    import subprocess
    harness, meta = FakeHarness(()), Meta()
    def runner(argv, **kwargs):
        if argv[0] == "git":
            return harness(argv, **kwargs)
        raise subprocess.TimeoutExpired(argv, 4500)
    result = run_tta(config, meta, runner=runner)
    assert result["status"] == "incomplete" and result["official_success"] is None
    assert not meta.calls


def test_second_attempt_cannot_be_reused_as_first(config):
    summary = run_tta(replace(config, attempts=2, mode="frozen"), runner=FakeHarness((False, False)))
    seed = Path(summary["attempts"][1]["attempt_dir"])
    cfg = replace(config, output_dir=config.output_dir.parent / "paired", seed_attempt_dir=seed)
    result = run_tta(cfg, Meta(), runner=FakeHarness(()))
    assert result["status"] == "incomplete"
    assert "first attempt" in result["error"]


def test_provenance_preserves_api_environment_variable_name(config):
    summary = run_tta(replace(config, attempts=1), runner=FakeHarness((False,)))
    evidence = read_attempt(summary["attempts"][0]["attempt_dir"])
    assert evidence["provenance"]["agent_options"] == [{"name": "api_key_env", "value": "OPENAI_API_KEY"}]


def test_cli_default_model_options_complete_a_sealed_attempt(config):
    kwargs = {"api_key_env": "DEEPSEEK_API_KEY", "temperature": 0.0, "max_output_tokens": 4096}
    cfg = replace(config, attempts=1, agent_kwargs=kwargs)
    summary = run_tta(cfg, runner=FakeHarness((False,)))
    assert summary["status"] == "exhausted"
    evidence = read_attempt(summary["attempts"][0]["attempt_dir"])
    assert {entry["name"]: entry["value"] for entry in evidence["provenance"]["agent_options"]} == kwargs


def test_candidate_text_and_digest_survive_persistence(config):
    class TextMeta(Meta):
        def propose(self, memory, instruction, trace, mode):
            candidate = super().propose(memory, instruction, trace, mode)
            candidate.candidate_memory["E"][0]["content"] = "Example command: API_KEY=placeholder"
            candidate.candidate_digest = memory_digest(candidate.candidate_memory)
            return candidate

    summary = run_tta(config, TextMeta(), runner=FakeHarness((False, True)))
    assert summary["status"] == "succeeded"
    proposal = json.loads((config.output_dir / "proposal-01.json").read_text(encoding="utf-8"))
    assert proposal["candidate_memory"]["E"][0]["content"] == "Example command: API_KEY=placeholder"
    assert memory_digest(proposal["candidate_memory"]) == proposal["candidate_digest"]
    assert load_memory(config.output_dir / "final-memory.json") == proposal["candidate_memory"]


def test_environment_endpoint_identity_is_hashed(config, monkeypatch):
    from hashlib import sha256
    endpoint = "https://user:placeholder@host/v1"
    monkeypatch.setenv("OPENAI_BASE_URL", endpoint)
    summary = run_tta(replace(config, attempts=1), runner=FakeHarness((False,)))
    evidence = read_attempt(summary["attempts"][0]["attempt_dir"])
    assert evidence["provenance"]["endpoint_environment"]["OPENAI_BASE_URL"] == sha256(endpoint.encode()).hexdigest()
    assert endpoint not in (config.output_dir / "campaign.json").read_text(encoding="utf-8")
