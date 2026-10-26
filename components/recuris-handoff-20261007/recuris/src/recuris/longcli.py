"""Native LongCLI-Bench BaseAgent adapter for the Recuris runner.

Load with ``tb run --agent-import-path recuris.longcli:RecurisAgent``.
Only this integration module requires the official LongCLI-Bench checkout.
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
        "The Recuris LongCLI adapter requires the official LongCLI-Bench checkout. "
        "Install it with `python -m pip install -e /path/to/longcli-bench` "
        "in the same Python environment as recuris."
    ) from exc

from .audit import JsonlLogger
from .client import ModelConfig, OpenAIChatClient
from .engine import RecurisConfig, RecurisRunner
from .memory import load_memory


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
    """Forward model actions only to the benchmark task's native tmux session."""

    def __init__(self, session: Any, max_duration: float = 120.0):
        if isinstance(max_duration, bool) or not isinstance(max_duration, (int, float)) or not math.isfinite(max_duration) or max_duration <= 0:
            raise ValueError("max_duration must be finite and positive")
        self.session = session
        self.max_duration = max_duration

    def observe(self) -> str:
        return self.session.get_incremental_output()

    def execute(self, keystrokes: str, duration: float) -> str:
        if not isinstance(keystrokes, str):
            raise TypeError("Terminal keystrokes must be a string")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
            raise ValueError("Terminal duration must be a finite nonnegative number")
        # Preserve newlines, heredocs, interactive keys and empty-key polling.
        # The actor supplies Enter as a newline; do not add or wrap commands.
        self.session.send_keys(
            keystrokes,
            block=False,
            min_timeout_sec=min(duration, self.max_duration),
        )
        return self.observe()


class RecurisAgent(BaseAgent):
    """Expose ModelConfig and RecurisConfig through native agent kwargs."""

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key_env: str = "DEEPSEEK_API_KEY",
        memory_path: str | None = None,
        **kwargs: Any,
    ):
        # Upstream tb supplies this for custom agents as well as built-in ones.
        kwargs.pop("no_rebuild", None)
        base_kwargs = {
            key: kwargs.pop(key)
            for key in ("version", "prompt_template")
            if key in kwargs
        }
        super().__init__(**base_kwargs)
        run_kwargs = _config_kwargs(RecurisConfig, kwargs)
        model_kwargs = _config_kwargs(ModelConfig, kwargs)
        model_kwargs.setdefault("temperature", 0.0)
        if kwargs:
            raise ValueError("Unknown Recuris agent kwargs: " + ", ".join(sorted(kwargs)))
        model_envs = (
            ("OPENAI_MODEL", "DEEPSEEK_MODEL")
            if api_key_env == "OPENAI_API_KEY"
            else ("DEEPSEEK_MODEL", "OPENAI_MODEL")
        )
        chosen_model = model_name or next(
            (os.environ[name] for name in model_envs if os.environ.get(name)), None
        )
        if not isinstance(chosen_model, str) or not chosen_model.strip():
            raise ValueError("Pass --model MODEL_ID or set DEEPSEEK_MODEL / OPENAI_MODEL")
        if memory_path is not None and not isinstance(memory_path, str):
            raise ValueError("memory_path must be a path string or null")
        self.memory_path = memory_path
        # Validate the supplied offline memory before any model or terminal call.
        load_memory(self.memory_path)
        self.run_config = RecurisConfig(**run_kwargs)
        self.model_config = ModelConfig(
            model_name=chosen_model,
            base_url=base_url,
            api_key_env=api_key_env,
            **model_kwargs,
        )

    @staticmethod
    def name() -> str:
        return "recuris"

    def perform_task(
        self,
        instruction: str,
        session: Any,
        logging_dir: Path | None = None,
    ) -> AgentResult:
        # Every harness feedback turn uses this same logging_dir with a fresh
        # agent. Preserve each invocation without sharing memory between turns.
        run_dir = None
        if logging_dir is not None:
            run_dir = Path(logging_dir) / "recuris" / uuid4().hex
            run_dir.mkdir(parents=True, exist_ok=False)
        logger = (
            JsonlLogger(run_dir, secrets=(os.environ.get(self.model_config.api_key_env, ""),))
            if run_dir else None
        )
        terminal = TmuxTerminal(session, self.run_config.max_command_duration)
        markers: list[tuple[float, str]] = []
        self._marker(session, markers, "Recuris start")
        result = RecurisRunner(
            OpenAIChatClient(self.model_config), self.run_config,
            memory=load_memory(self.memory_path), logger=logger,
        ).run(self._render_instruction(instruction), terminal)
        self._marker(session, markers, f"Recuris stop: {result.stop_reason}")
        # Local task completion or budget stops do not establish official success.
        # The harness owns test feedback and final grading.
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
            # Optional recording must not terminate agent execution.
            pass
