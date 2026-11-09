"""Offline tests load the actual pinned upstream BaseAgent and AgentResult.

These tests verify the agent interface and terminal behavior, not real Docker
execution or LongCLI task correctness. Tmux and template dependencies are mocked.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from retrac.engine import RunResult


@pytest.fixture
def adapter(monkeypatch):
    for name in ("terminal_bench", "terminal_bench.agents", "terminal_bench.terminal", "terminal_bench.utils"):
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    tmux = ModuleType("terminal_bench.terminal.tmux_session")
    tmux.TmuxSession = FakeSession
    template = ModuleType("terminal_bench.utils.template_utils")
    template.render_prompt_template = lambda path, instruction: instruction
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
    monkeypatch.delitem(sys.modules, "retrac.longcli", raising=False)
    loaded = importlib.import_module("retrac.longcli")
    yield loaded
    sys.modules.pop("retrac.longcli", None)


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


@pytest.mark.parametrize("duration", [-1, float("inf"), float("nan"), True])
def test_tmux_rejects_invalid_wait_without_sending(adapter, duration):
    session = FakeSession()
    with pytest.raises(ValueError):
        adapter.TmuxTerminal(session).execute("ls\n", duration)
    assert session.calls == []


def test_cli_kwargs_and_model_environment(adapter, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "provider-model-id")
    agent = adapter.RetracAgent(
        rounds="3",
        max_total_seconds="600",
        max_output_tokens="1024",
        temperature="0.2",
        extra_body='{"thinking":{"type":"disabled"}}',
        no_rebuild=True,
    )
    assert isinstance(agent, adapter.BaseAgent)
    assert agent.name() == "retrac"
    assert agent.run_config.rounds == 3
    assert agent.run_config.max_total_seconds == 600.0
    assert agent.model_config.model_name == "provider-model-id"
    assert agent.model_config.api_key_env == "DEEPSEEK_API_KEY"
    assert agent.model_config.max_output_tokens == 1024
    assert agent.model_config.temperature == 0.2
    assert agent.model_config.extra_body == {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize("kwargs", [
    {"rounds": "typo"}, {"rounds": False}, {"rounds": 1.5},
    {"max_total_seconds": "nan"}, {"extra_body": "[]"},
    {"round": 3}, {"temperature": "nan"},
])
def test_bad_agent_kwargs_fail_early(adapter, kwargs):
    with pytest.raises(ValueError):
        adapter.RetracAgent(model_name="model", **kwargs)


def test_model_must_be_explicit(adapter, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    with pytest.raises(ValueError, match="--model"):
        adapter.RetracAgent()


def test_perform_task_reports_usage_and_retains_each_harness_turn(adapter, monkeypatch, tmp_path):
    captures = []

    class Runner:
        def __init__(self, client, config, logger=None):
            captures.append((client, config, logger))
            self.logger = logger

        def run(self, instruction, terminal):
            assert instruction == "implement feature"
            terminal.execute("ls\n", 0)
            result = RunResult(
                input_tokens=120, output_tokens=30,
                stop_reason="rounds_completed", final_answer="finished",
            )
            self.logger.save("result.json", result)
            return result

    monkeypatch.setattr(adapter, "RetracRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    agent = adapter.RetracAgent(model_name="model", rounds=2)
    session = FakeSession()
    first = agent.perform_task("implement feature", session, tmp_path)
    second = agent.perform_task("implement feature", session, tmp_path)
    assert first.total_input_tokens == second.total_input_tokens == 120
    assert first.total_output_tokens == 30
    assert first.failure_mode is adapter.FailureMode.NONE
    assert len(first.timestamped_markers) == 2
    assert len(session.calls) == 2
    logs = list((tmp_path / "retrac").glob("*/result.json"))
    assert len(logs) == 2
    assert json.loads(logs[0].read_text(encoding="utf-8"))["official_success"] is None
    assert captures[0][1].rounds == 2


@pytest.mark.parametrize("reason,error,expected", [
    ("protocol_error", "bad output", "fatal_llm_parse_error"),
    ("terminal_error", "broken session", "unknown_agent_error"),
    ("model_error", "unavailable", "unknown_agent_error"),
    ("compression_error", "invalid state", "unknown_agent_error"),
    ("max_total_seconds_reached", None, "agent_timeout"),
    ("max_tool_calls_reached", None, "none"),
])
def test_failure_mapping(adapter, monkeypatch, reason, error, expected):
    class Runner:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, *args):
            return RunResult(stop_reason=reason, error=error)

    monkeypatch.setattr(adapter, "RetracRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    result = adapter.RetracAgent(model_name="model").perform_task("task", FakeSession())
    assert result.failure_mode.value == expected
