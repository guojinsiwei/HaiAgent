"""LongCLI-Bench's native BaseAgent adapter.

Load with ``tb run --agent-import-path retrac.longcli:RetracAgent``.  This
module alone needs the LongCLI-Bench fork of terminal_bench installed; the
RE-TRAC engine and offline tests do not depend on the evaluation harness.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import fields
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints
from uuid import uuid4

try:
    from terminal_bench.agents.base_agent import AgentResult, BaseAgent
    from terminal_bench.agents.failure_mode import FailureMode
except ImportError as exc:
    raise ImportError(
        "The LongCLI adapter requires the official LongCLI-Bench checkout. "
        "Install that checkout with `python -m pip install -e /path/to/longcli-bench` "
        "in the same environment as retrac."
    ) from exc

from .audit import JsonlLogger
from .client import ModelConfig, OpenAIChatClient
from .engine import RetracConfig, RetracRunner


def _coerce_kwarg(name: str, value: Any, annotation: Any) -> Any:
    """Accept both native CLI primitives and programmatic string kwargs."""
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        alternatives = get_args(annotation)
        if type(None) in alternatives and (
            value is None or isinstance(value, str) and value.lower() == "null"
        ):
            return None
        for alternative in alternatives:
            if alternative is not type(None):
                try:
                    return _coerce_kwarg(name, value, alternative)
                except (TypeError, ValueError):
                    pass
        raise ValueError(f"Invalid value for agent kwarg {name!r}: {value!r}")
    if annotation is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise ValueError(f"{name} must be true or false")
    if annotation is int:
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError(f"{name} must be an integer")
        return int(value)
    if annotation is float:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a finite number")
        converted = float(value)
        if not math.isfinite(converted):
            raise ValueError(f"{name} must be a finite number")
        return converted
    if origin is dict or annotation is dict:
        converted = json.loads(value) if isinstance(value, str) else value
        if not isinstance(converted, dict):
            raise ValueError(f"{name} must be a JSON object")
        return converted
    if annotation is str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        return value
    return value


def _config_kwargs(config_type: type, kwargs: dict[str, Any]) -> dict[str, Any]:
    annotations = get_type_hints(config_type)
    return {
        field.name: _coerce_kwarg(field.name, kwargs.pop(field.name), annotations[field.name])
        for field in fields(config_type)
        if field.name in kwargs
    }


class TmuxTerminal:
    """Use only the task's native Docker/tmux session for model actions."""

    def __init__(self, session: Any, max_duration: float = 120.0):
        self.session = session
        self.max_duration = max_duration

    def observe(self) -> str:
        return self.session.get_incremental_output()

    def execute(self, keystrokes: str, duration: float) -> str:
        if not isinstance(keystrokes, str):
            raise TypeError("Terminal keystrokes must be a string")
        if isinstance(duration, bool) or not math.isfinite(duration) or duration < 0:
            raise ValueError("Terminal duration must be a finite nonnegative number")
        # Do not append Enter, split newlines, or wrap in `bash -c`: all three
        # would alter interactive commands, Ctrl-C, and heredoc semantics.
        self.session.send_keys(
            keystrokes,
            block=False,
            min_timeout_sec=min(duration, self.max_duration),
        )
        return self.observe()


class RetracAgent(BaseAgent):
    """Native import-path agent; kwargs expose ModelConfig and RetracConfig."""

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "DEEPSEEK_API_KEY",
        **kwargs: Any,
    ):
        # The upstream CLI always supplies no_rebuild, including custom agents.
        kwargs.pop("no_rebuild", None)
        base_kwargs = {
            key: kwargs.pop(key)
            for key in ("version", "prompt_template")
            if key in kwargs
        }
        super().__init__(**base_kwargs)
        run_kwargs = _config_kwargs(RetracConfig, kwargs)
        model_kwargs = _config_kwargs(ModelConfig, kwargs)
        if kwargs:
            raise ValueError("Unknown RE-TRAC agent kwargs: " + ", ".join(sorted(kwargs)))
        chosen_model = model_name or os.environ.get("DEEPSEEK_MODEL")
        if not chosen_model or not chosen_model.strip():
            raise ValueError("Pass --model MODEL_ID or set DEEPSEEK_MODEL")
        self.run_config = RetracConfig(**run_kwargs)
        self.model_config = ModelConfig(
            model_name=chosen_model,
            base_url=base_url,
            api_key_env=api_key_env,
            **model_kwargs,
        )

    @staticmethod
    def name() -> str:
        return "retrac"

    def perform_task(
        self,
        instruction: str,
        session: Any,
        logging_dir: Path | None = None,
    ) -> AgentResult:
        # The harness reuses logging_dir across --give-test-output turns. A
        # unique subdirectory keeps every inner trajectory and token count.
        run_dir = None
        if logging_dir is not None:
            run_dir = Path(logging_dir) / "retrac" / uuid4().hex
            run_dir.mkdir(parents=True, exist_ok=False)
        logger = (
            JsonlLogger(run_dir, secrets=(os.environ.get(self.model_config.api_key_env, ""),))
            if run_dir else None
        )
        terminal = TmuxTerminal(session, self.run_config.max_command_duration)
        markers: list[tuple[float, str]] = []
        self._marker(session, markers, "RE-TRAC start")
        result = RetracRunner(
            OpenAIChatClient(self.model_config), self.run_config, logger=logger
        ).run(self._render_instruction(instruction), terminal)
        self._marker(session, markers, f"RE-TRAC stop: {result.stop_reason}")
        # NONE means the agent returned normally; it does not assert benchmark
        # success. F2P/P2P correctness is determined only by the official tests.
        failure_mode = FailureMode.NONE
        if result.stop_reason == "protocol_error":
            failure_mode = FailureMode.FATAL_LLM_PARSE_ERROR
        elif result.stop_reason == "max_total_seconds_reached":
            failure_mode = FailureMode.AGENT_TIMEOUT
        elif result.error is not None:
            failure_mode = FailureMode.UNKNOWN_AGENT_ERROR
        return AgentResult(
            total_input_tokens=result.input_tokens,
            total_output_tokens=result.output_tokens,
            failure_mode=failure_mode,
            timestamped_markers=markers,
        )

    @staticmethod
    def _marker(session: Any, markers: list[tuple[float, str]], text: str) -> None:
        try:
            markers.append((session.get_asciinema_timestamp(), text))
        except Exception:
            # Optional recording telemetry must not terminate task execution.
            pass
