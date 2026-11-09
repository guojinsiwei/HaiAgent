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

from reflexion.engine import RunResult


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
    monkeypatch.delitem(sys.modules, "reflexion.longcli", raising=False)
    loaded = importlib.import_module("reflexion.longcli")
    yield loaded
    sys.modules.pop("reflexion.longcli", None)


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
    agent = adapter.ReflexionAgent(
        max_trials="3",
        memory_size="2",
        max_total_seconds="600",
        max_output_tokens="1024",
        temperature="0.2",
        extra_body='{"thinking":{"type":"disabled"}}',
        no_rebuild=True,
    )
    assert isinstance(agent, adapter.BaseAgent)
    assert agent.name() == "reflexion"
    assert agent.run_config.max_trials == 3
    assert agent.run_config.memory_size == 2
    assert agent.run_config.max_total_seconds == 600.0
    assert agent.model_config.model_name == "provider-model-id"
    assert agent.model_config.api_key_env == "DEEPSEEK_API_KEY"
    assert agent.model_config.max_output_tokens == 1024
    assert agent.model_config.temperature == 0.2
    assert agent.model_config.extra_body == {"thinking": {"type": "disabled"}}


def test_openai_environment_is_selected_explicitly(adapter, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-id")
    monkeypatch.setenv("OPENAI_MODEL", "openai-id")
    agent = adapter.ReflexionAgent(api_key_env="OPENAI_API_KEY", base_url="https://api.openai.com/v1")
    assert agent.model_config.model_name == "openai-id"
    assert agent.model_config.api_key_env == "OPENAI_API_KEY"
    assert agent.model_config.base_url == "https://api.openai.com/v1"
    explicit = adapter.ReflexionAgent(model_name="override", api_key_env="OPENAI_API_KEY")
    assert explicit.model_config.model_name == "override"


@pytest.mark.parametrize("kwargs", [
    {"max_trials": "typo"}, {"max_trials": False}, {"max_trials": 1.5},
    {"max_total_seconds": "nan"}, {"extra_body": "[]"},
    {"max_trial": 3}, {"temperature": "nan"}, {"max_total_seconds": True},
])
def test_bad_agent_kwargs_fail_early(adapter, kwargs):
    with pytest.raises(ValueError):
        adapter.ReflexionAgent(model_name="model", **kwargs)


def test_model_must_be_explicit(adapter, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(ValueError, match="--model"):
        adapter.ReflexionAgent()


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
                stop_reason="evaluator_passed", final_answer="finished",
            )
            self.logger.save("result.json", result)
            return result

    monkeypatch.setattr(adapter, "ReflexionRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    agent = adapter.ReflexionAgent(model_name="model", max_trials=2)
    session = FakeSession()
    first = agent.perform_task("implement feature", session, tmp_path)
    second = agent.perform_task("implement feature", session, tmp_path)
    assert isinstance(first, adapter.AgentResult)
    assert first.total_input_tokens == second.total_input_tokens == 120
    assert first.total_output_tokens == 30
    assert first.failure_mode is adapter.FailureMode.NONE
    assert len(first.timestamped_markers) == 2
    assert len(session.calls) == 2
    logs = list((tmp_path / "reflexion").glob("*/result.json"))
    assert len(logs) == 2
    assert json.loads(logs[0].read_text(encoding="utf-8"))["official_success"] is None
    assert captures[0][1].max_trials == 2


@pytest.mark.parametrize("reason,error,expected", [
    ("protocol_error", "bad output", "fatal_llm_parse_error"),
    ("terminal_error", "broken session", "unknown_agent_error"),
    ("model_error", "unavailable", "unknown_agent_error"),
    ("reflection_error", "invalid memory", "unknown_agent_error"),
    ("max_total_seconds_reached", None, "agent_timeout"),
    ("max_tool_calls_reached", None, "none"),
    ("max_trials_reached", None, "none"),
    ("evaluator_passed", None, "none"),
])
def test_failure_mapping(adapter, monkeypatch, reason, error, expected):
    class Runner:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, *args):
            return RunResult(stop_reason=reason, error=error)

    monkeypatch.setattr(adapter, "ReflexionRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    result = adapter.ReflexionAgent(model_name="model").perform_task("task", FakeSession())
    assert result.failure_mode.value == expected


def test_prompt_template_and_missing_recording_are_supported(adapter, monkeypatch):
    class Runner:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, instruction, terminal):
            assert instruction == "Template: task"
            return RunResult(stop_reason="max_trials_reached")

    class NoRecording(FakeSession):
        def get_asciinema_timestamp(self):
            raise RuntimeError("Recording disabled")

    monkeypatch.setattr(adapter, "ReflexionRunner", Runner)
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: config)
    agent = adapter.ReflexionAgent(model_name="model", prompt_template="custom.j2", version="test")
    result = agent.perform_task("task", NoRecording())
    assert result.timestamped_markers == []
    assert result.failure_mode is adapter.FailureMode.NONE
    assert agent.version == "test"


def test_native_adapter_runs_real_reflexion_loop_and_accounts_for_every_role(adapter, monkeypatch, tmp_path):
    """Exercise adapter -> real runner -> tmux bridge -> native AgentResult."""
    from collections import deque
    from copy import deepcopy

    from reflexion.client import ModelReply
    from reflexion.engine import ReflexionRunner

    lesson = "I must repair the artifact and rerun the public smoke test before finishing."
    feedback = "The observed public smoke test still fails."

    def action(command=None, answer=""):
        return json.dumps({
            "analysis": "Use observed public test evidence.",
            "commands": [] if command is None else [{"keystrokes": command, "duration": 0}],
            "task_complete": command is None,
            "final_answer": answer,
        })

    scripted = [
        ("act", action("python smoke_test.py\n")),
        ("act", action(answer="The initial attempt is ready for review.")),
        ("evaluate", json.dumps({"passed": False, "feedback": feedback, "evidence": ["PUBLIC_TEST: fail"]})),
        ("reflect", lesson),
        ("act", action("python repair_and_check.py\n")),
        ("act", action(answer="The repaired artifact passes the public smoke test.")),
        ("evaluate", json.dumps({"passed": True, "feedback": "The observed public test passes.", "evidence": ["PUBLIC_TEST: pass"]})),
    ]

    class ScriptedClient:
        def __init__(self):
            self.steps = deque(scripted)
            self.requests = []

        def complete(self, messages, *, purpose, deadline_monotonic=None):
            expected_purpose, content = self.steps.popleft()
            assert purpose == expected_purpose
            assert deadline_monotonic is not None
            self.requests.append({"purpose": purpose, "messages": deepcopy(messages)})
            call = len(self.requests)
            # Distinct usage makes omitted evaluator/reflection accounting visible.
            return ModelReply(content, input_tokens=10 + call, output_tokens=call)

    class EvidenceSession(FakeSession):
        def __init__(self):
            super().__init__()
            self.outputs = deque([
                "artifact is incomplete", "PUBLIC_TEST: fail",
                "PUBLIC_TEST: fail", "PUBLIC_TEST: pass",
            ])

        def get_incremental_output(self):
            self.observations += 1
            return self.outputs.popleft()

    client = ScriptedClient()
    monkeypatch.setattr(adapter, "OpenAIChatClient", lambda config: client)
    assert adapter.ReflexionRunner is ReflexionRunner
    session = EvidenceSession()
    native_result = adapter.ReflexionAgent(model_name="offline-model", max_trials=3).perform_task(
        "Repair the artifact and pass its public smoke test.", session, tmp_path,
    )

    expected_purposes = [purpose for purpose, _ in scripted]
    assert not client.steps and not session.outputs
    assert [request["purpose"] for request in client.requests] == expected_purposes
    assert session.calls == [
        ("python smoke_test.py\n", {"block": False, "min_timeout_sec": 0.0}),
        ("python repair_and_check.py\n", {"block": False, "min_timeout_sec": 0.0}),
    ]
    assert session.observations == 4
    reflection_request = client.requests[3]["messages"][1]["content"]
    assert feedback in reflection_request and "PUBLIC_TEST: fail" in reflection_request
    retry_messages = client.requests[4]["messages"]
    assert [message["role"] for message in retry_messages] == ["system", "user", "user"]
    assert lesson in retry_messages[1]["content"]
    assert "PUBLIC_TEST: fail" in retry_messages[2]["content"]
    assert "python smoke_test.py" not in json.dumps(retry_messages)

    assert isinstance(native_result, adapter.AgentResult)
    assert native_result.failure_mode is adapter.FailureMode.NONE
    assert (native_result.total_input_tokens, native_result.total_output_tokens) == (98, 28)
    assert len(native_result.timestamped_markers) == 2
    saved_paths = list((tmp_path / "reflexion").glob("*/result.json"))
    assert len(saved_paths) == 1
    saved = json.loads(saved_paths[0].read_text(encoding="utf-8"))
    assert saved["stop_reason"] == "evaluator_passed"
    assert saved["official_success"] is None
    assert saved["model_calls"] == 7 and saved["tool_calls"] == 2
    assert (saved["input_tokens"], saved["output_tokens"]) == (98, 28)
    assert saved["memory"] == [lesson]
    assert saved["trials"][0]["evaluation"]["passed"] is False
    assert saved["trials"][0]["reflection"] == lesson
    assert saved["trials"][1]["memory_before"] == [lesson]
    assert saved["trials"][1]["evaluation"]["passed"] is True
    assert len(saved["trials"]) == 2
    events = [json.loads(line) for line in saved_paths[0].with_name("events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["purpose"] for event in events if event["event"] == "model_request"] == expected_purposes
