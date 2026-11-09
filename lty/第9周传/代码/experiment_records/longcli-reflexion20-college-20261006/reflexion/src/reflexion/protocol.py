"""Strict, all-or-nothing parsing before any model-generated action is sent."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import re
from typing import Any

from .response_text import ReasoningPrefixError, strip_reasoning_prefix


class ProtocolError(ValueError):
    pass


def response_text(content: str) -> str:
    if not isinstance(content, str):
        raise ProtocolError("Response must be text")
    try:
        return strip_reasoning_prefix(content).strip()
    except ReasoningPrefixError as exc:
        raise ProtocolError(str(exc)) from exc


def _object(content: str) -> dict[str, Any]:
    text = response_text(content)
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)[:-3].strip()
    def unique_pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProtocolError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result
    try:
        data = json.loads(text, object_pairs_hook=unique_pairs)
    except ValueError as exc:
        raise ProtocolError(f"Return exactly one valid JSON object: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("Response must be a JSON object")
    return data


@dataclass(frozen=True)
class Command:
    keystrokes: str
    duration: float


@dataclass(frozen=True)
class Action:
    analysis: str
    commands: list[Command]
    task_complete: bool
    final_answer: str


@dataclass(frozen=True)
class Evaluation:
    passed: bool
    feedback: str
    evidence: list[str] = field(default_factory=list)
    source: str = "model_self_evaluation"

    def __post_init__(self):
        if type(self.passed) is not bool or not isinstance(self.feedback, str) or not self.feedback.strip():
            raise ProtocolError("Evaluation needs a boolean passed and nonempty feedback")
        if not isinstance(self.evidence, list) or not all(isinstance(x, str) and x.strip() for x in self.evidence):
            raise ProtocolError("Evidence must be a list of nonempty strings")
        if self.passed and not self.evidence:
            raise ProtocolError("A pass needs observed supporting evidence")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ProtocolError("Evaluation source must be nonempty")


def parse_action(content: str, max_duration: float = 120) -> Action:
    data = _object(content)
    if set(data) != {"analysis", "commands", "task_complete", "final_answer"}:
        raise ProtocolError("Action requires exactly analysis, commands, task_complete, final_answer")
    if not isinstance(data["analysis"], str) or not isinstance(data["final_answer"], str):
        raise ProtocolError("analysis and final_answer must be strings")
    if type(data["task_complete"]) is not bool or not isinstance(data["commands"], list):
        raise ProtocolError("task_complete must be a boolean and commands an array")
    commands = []
    for item in data["commands"]:
        if not isinstance(item, dict) or set(item) != {"keystrokes", "duration"}:
            raise ProtocolError("Each command requires exactly keystrokes and duration")
        keys, duration = item["keystrokes"], item["duration"]
        if not isinstance(keys, str) or "\x00" in keys:
            raise ProtocolError("keystrokes must be a string without NUL")
        # Range-check integers before converting them in math.isfinite: JSON may
        # contain integers too large to fit in a platform float.
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 0 <= duration <= max_duration or not math.isfinite(duration):
            raise ProtocolError(f"duration must be finite and in [0, {max_duration}]")
        commands.append(Command(keys, float(duration)))
    if data["task_complete"] and commands:
        raise ProtocolError("Observe command results before finishing: completion requires commands=[]")
    if not data["task_complete"] and not commands:
        raise ProtocolError("Provide a command, an empty-keystrokes poll, or task_complete=true")
    return Action(data["analysis"], commands, data["task_complete"], data["final_answer"])


def parse_evaluation(content: str) -> Evaluation:
    data = _object(content)
    if set(data) != {"passed", "feedback", "evidence"}:
        raise ProtocolError("Evaluation requires exactly passed, feedback, evidence")
    return Evaluation(**data)
