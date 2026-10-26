"""Offline integration against the actual pinned upstream agent definitions.

Only tmux and template dependencies are mocked. No Docker or model API runs.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from recuris.engine import RunResult


@pytest.fixture
def adapter(monkeypatch):
    for name in ("terminal_bench", "terminal_bench.agents", "terminal_bench.terminal", "terminal_bench.utils"):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    tmux = ModuleType("terminal_bench.terminal.tmux_session")
    tmux.TmuxSession = FakeSession
    template = ModuleType("terminal_bench.utils.template_utils")
    template.render_prompt_template = lambda path, instruction: f"Template: {instruction}"
    monkeypatch.setitem(sys.modules, tmux.__name__, tmux)
    monkeypatch.setitem(sys.modules, template.__name__, template)
    fixtures = Path(__file__).resolve().parents[1] / "vendor-contracts"
    for name in ("failure_mode", "base_agent"):
        module_name = f"terminal_bench.agents.{name}"
        spec = importlib.util.spec_from_file_location(
            module_name, fixtures / f"terminal_bench__agents__{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, module_name, module)
        spec.loader.exec_module(module)
    monkeypatch.delitem(sys.modules, "recuris.longcli", raising=False)
    loaded = importlib.import_module("recuris.longcli")
    yield loaded
    sys.modules.pop("recuris.longcli", None)


class FakeSession:
    def __init__(self):
        self.calls = []
        self.observations = 0

    def send_keys(self, keys, **kwargs):
        self.calls.append((keys, kwargs))

    def get_incremental_output(self):
        self.observations += 1
        return f"screen {self.observations}"

    def get_asciinema_timestamp(self):
        return 1.5


def test_tmux_forwards_interactive_keys_unchanged(adapter):
    session = FakeSession()
    terminal = adapter.TmuxTerminal(session, max_duration=10)
    keys = "cat > code.py <<'PY'\nprint('hello')\nPY\n"
    assert terminal.execute(keys, 0.5) == "screen 1"
    terminal.execute("C-c", 0)
    terminal.execute("", 300)
    assert session.calls == [
        (keys, {"block": False, "min_timeout_sec": 0.5}),
        ("C-c", {"block": False, "min_timeout_sec": 0}),
        ("", {"block": False, "min_timeout_sec": 10}),
    ]


@pytest.mark.parametrize("duration", [-1, float("inf"), float("nan"), True, "3", None])
def test_tmux_rejects_invalid_wait_without_sending(adapter, duration):
    session = FakeSession()
    with pytest.raises(ValueError):
        adapter.TmuxTerminal(session).execute("ls\n", duration)
    assert session.calls == []


def test_cli_kwargs_and_model_environment(adapter, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "provider-model-id")
    agent = adapter.RecurisAgent(
        max_steps="30",
        history_turns="2",
        max_total_seconds="600",
        max_output_tokens="1024",
        temperature="0.2",
        extra_body='{"thinking":{"type":"disabled"}}',
        no_rebuild=True,
    )
    assert isinstance(agent, adapter.BaseAgent)
    assert agent.name() == "recuris"
    assert agent.run_config.max_steps == 30
    assert agent.run_config.history_turns == 2
    assert agent.run_config.max_total_seconds == 600.0
    assert agent.model_config.model_name == "provider-model-id"
    assert agent.model_config.api_key_env == "DEEPSEEK_API_KEY"
    assert agent.model_config.max_output_tokens == 1024
    assert agent.model_config.temperature == 0.2
    assert agent.model_config.extra_body == {"thinking": {"type": "disabled"}}


def test_openai_environment_is_selected_explicitly(adapter, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-id")
    monkeypatch.setenv("OPENAI_MODEL", "openai-id")
    agent = adapter.RecurisAgent(api_key_env="OPENAI_API_KEY", base_url="https://api.openai.com/v1")
    assert agent.model_config.model_name == "openai-id"
    assert agent.model_config.api_key_env == "OPENAI_API_KEY"
    assert agent.model_config.base_url == "https://api.openai.com/v1"
    explicit = adapter.RecurisAgent(model_name="override", api_key_env="OPENAI_API_KEY")
    assert explicit.model_config.model_name == "override"


def test_paper_temperature_defaults_to_zero_and_allows_explicit_null(adapter):
    assert adapter.RecurisAgent(model_name="model").model_config.temperature == 0.0
    assert adapter.RecurisAgent(model_name="model", temperature="null").model_config.temperature is None
    assert adapter.RecurisAgent(model_name="model", temperature=None).model_config.temperature is None


@pytest.mark.parametrize("kwargs", [
    {"max_steps": "typo"}, {"max_steps": False}, {"max_steps": 1.5},
    {"max_total_seconds": "nan"}, {"extra_body": "[]"},
    {"max_step": 3}, {"temperature": "nan"}, {"max_total_seconds": True},
])
def test_bad_agent_kwargs_fail_early(adapter, kwargs):
    with pytest.raises(ValueError):
        adapter.RecurisAgent(model_name="model", **kwargs)


def test_model_must_be_explicit(adapter, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ValueError, match="--model"):
        adapter.RecurisAgent()


def test_offline_memory_is_loaded_independently_for_each_harness_turn(adapter, monkeypatch):
    loads = []
    memories = []

    def load(path):
        loads.append(path)
        return {"skills": ["initial skill"], "episodes": []}

    class Runner:
        def __init__(self, client, config, memory=None, logger=None):
            memories.append(memory)

        def run(self, *args):
            assert memories[-1]["episodes"] == []
            memories[-1]["episodes"].append("local execution")
            return RunResult(stop_reason="task_complete")

    monkeypatch.setattr(adapter, "load_memory", load)
    monkeypatch.setattr(adapter, "RecurisRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    agent = adapter.RecurisAgent(model_name="model", memory_path="offline.json")
    agent.perform_task("first task", FakeSession())
    agent.perform_task("second task", FakeSession())
    assert loads == ["offline.json", "offline.json", "offline.json"]
    assert len(memories) == 2 and memories[0] is not memories[1]


def test_invalid_offline_memory_fails_before_transport(adapter, monkeypatch):
    def reject(path):
        raise ValueError("invalid offline memory")

    monkeypatch.setattr(adapter, "load_memory", reject)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: pytest.fail("unexpected client"))
    with pytest.raises(ValueError, match="invalid offline memory"):
        adapter.RecurisAgent(model_name="model", memory_path="bad.json")


@pytest.mark.parametrize("path", [False, 42, {}])
def test_memory_path_type_is_checked(adapter, path):
    with pytest.raises(ValueError, match="memory_path"):
        adapter.RecurisAgent(model_name="model", memory_path=path)


def test_perform_task_reports_usage_and_retains_each_harness_turn(adapter, monkeypatch, tmp_path):
    captures = []

    class Runner:
        def __init__(self, client, config, memory=None, logger=None):
            captures.append((client, config, memory, logger))
            self.logger = logger

        def run(self, instruction, terminal):
            assert instruction == "implement feature"
            terminal.execute("ls\n", 0)
            result = RunResult(
                input_tokens=120, output_tokens=30,
                stop_reason="task_complete", final_answer="finished",
            )
            self.logger.save("result.json", result)
            return result

    monkeypatch.setattr(adapter, "RecurisRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    agent = adapter.RecurisAgent(model_name="model", max_steps=2)
    session = FakeSession()
    first = agent.perform_task("implement feature", session, tmp_path)
    second = agent.perform_task("implement feature", session, tmp_path)
    assert isinstance(first, adapter.AgentResult)
    assert first.total_input_tokens == second.total_input_tokens == 120
    assert first.total_output_tokens == 30
    assert first.failure_mode is adapter.FailureMode.NONE
    assert len(first.timestamped_markers) == 2
    assert len(session.calls) == 2
    logs = list((tmp_path / "recuris").glob("*/result.json"))
    assert len(logs) == 2
    assert json.loads(logs[0].read_text(encoding="utf-8"))["official_success"] is None
    assert captures[0][1].max_steps == 2


@pytest.mark.parametrize("reason,error,expected", [
    ("protocol_error", "bad output", "fatal_llm_parse_error"),
    ("terminal_error", "broken session", "unknown_agent_error"),
    ("model_error", "unavailable", "unknown_agent_error"),
    ("verification_error", "invalid verification", "unknown_agent_error"),
    ("max_total_seconds_reached", None, "agent_timeout"),
    ("max_tool_calls_reached", None, "none"),
    ("max_steps_reached", None, "none"),
    ("task_complete", None, "none"),
    ("actor_stopped_incomplete", None, "none"),
    ("max_model_calls_reached", None, "none"),
])
def test_failure_mapping(adapter, monkeypatch, reason, error, expected):
    class Runner:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, *args):
            return RunResult(stop_reason=reason, error=error)

    monkeypatch.setattr(adapter, "RecurisRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    result = adapter.RecurisAgent(model_name="model").perform_task("task", FakeSession())
    assert result.failure_mode.value == expected


def test_prompt_template_and_missing_recording_are_supported(adapter, monkeypatch):
    class Runner:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, instruction, terminal):
            assert instruction == "Template: task"
            return RunResult(stop_reason="max_steps_reached")

    class NoRecording(FakeSession):
        def get_asciinema_timestamp(self):
            raise RuntimeError("Recording disabled")

    monkeypatch.setattr(adapter, "RecurisRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    agent = adapter.RecurisAgent(model_name="model", prompt_template="custom.j2", version="test")
    result = agent.perform_task("task", NoRecording())
    assert result.timestamped_markers == []
    assert result.failure_mode is adapter.FailureMode.NONE
    assert agent.version == "test"


def test_native_adapter_runs_real_kernel_with_public_receipts_and_complete_usage(adapter, monkeypatch, tmp_path):
    """Exercise adapter -> real runner -> tmux bridge -> native AgentResult."""
    from collections import deque
    from copy import deepcopy
    import re

    from recuris.client import ModelReply
    from recuris.engine import RecurisRunner

    def action(operation, keys="", goal_id="", answer=""):
        return {"analysis": "Use public terminal evidence.", "operation": operation,
                "keystrokes": keys, "duration": 0, "goal_id": goal_id, "final_answer": answer}

    def update(status, evidence):
        return {"updates": [{"goal_id": "g1", "status": status, "evidence_ids": evidence, "blocker": ""}],
                "new_goals": [], "revised_verifications": []}

    scripted = [
        ("initialize", {"goals": [{"id": "g1", "description": "Pass artifact smoke check", "verification": {
            "command": "python public_smoke.py", "contains": ["PUBLIC_OK"]}}]}),
        ("act", action("execute", "python repair.py\n")),
        ("update", update("pending", [])),
        ("act", action("verify", goal_id="g1")),
        ("update", update("done", ["receipt-2"])),
        ("act", action("finish", answer="The public artifact check passed.")),
    ]

    class Client:
        def __init__(self):
            self.steps = deque(scripted)
            self.requests = []

        def complete(self, messages, *, purpose, deadline_monotonic=None):
            expected, content = self.steps.popleft()
            assert purpose == expected and deadline_monotonic is not None
            self.requests.append((purpose, deepcopy(messages)))
            count = len(self.requests)
            return ModelReply(json.dumps(content), input_tokens=10 + count, output_tokens=count)

    class EvidenceSession(FakeSession):
        output = "shell ready"

        def send_keys(self, keys, **kwargs):
            super().send_keys(keys, **kwargs)
            nonce = re.search(r"__RECURIS_([0-9a-f]{32})__=", keys)
            self.output = (
                "\n__RECURIS_BEGIN_" + nonce[1] + "__\nPUBLIC_OK\n__RECURIS_" + nonce[1] + "__=0\n"
                if nonce else "artifact repaired"
            )

        def get_incremental_output(self):
            self.observations += 1
            return self.output

    client, session = Client(), EvidenceSession()
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: client)
    assert adapter.RecurisRunner is RecurisRunner
    result = adapter.RecurisAgent(model_name="offline-model").perform_task("Repair artifact", session, tmp_path)
    assert isinstance(result, adapter.AgentResult)
    assert result.failure_mode is adapter.FailureMode.NONE
    assert not client.steps
    assert (result.total_input_tokens, result.total_output_tokens) == (81, 21)
    assert session.calls[0] == ("python repair.py\n", {"block": False, "min_timeout_sec": 0})
    assert len(session.calls) == 2 and session.observations == 3
    assert "command bash -c" in session.calls[1][0]
    saved_paths = list((tmp_path / "recuris").glob("*/result.json"))
    assert len(saved_paths) == 1
    saved = json.loads(saved_paths[0].read_text(encoding="utf-8"))
    assert saved["stop_reason"] == "task_complete"
    assert saved["official_success"] is None
    assert saved["model_calls"] == 6 and saved["tool_calls"] == 2
    assert saved["working_state"][0]["evidence_ids"] == ["receipt-2"]
    assert saved["trace"][1]["checker_decisions"][0]["accepted"] is True
    assert [purpose for purpose, _ in client.requests] == [purpose for purpose, _ in scripted]
