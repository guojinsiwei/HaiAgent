"""Strict JSON decoding shared by the fixed execution and evolution kernels."""
from __future__ import annotations
import json
import math
import re
from typing import Any
from .response_text import ReasoningPrefixError, strip_reasoning_prefix


class ProtocolError(ValueError):
    pass


def parse_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise ProtocolError("Expected text")
    try:
        text = strip_reasoning_prefix(text).strip()
    except ReasoningPrefixError as exc:
        raise ProtocolError(str(exc)) from exc
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)[:-3].strip()
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProtocolError("Duplicate JSON key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ProtocolError(f"Non-finite JSON constant: {value}")
    try:
        result = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"Expected one valid JSON object: {exc}") from exc
    if not isinstance(result, dict):
        raise ProtocolError("Expected a JSON object")
    return result


def exact_keys(value: Any, keys: set[str], label: str):
    if not isinstance(value, dict) or set(value) != keys:
        raise ProtocolError(f"{label} requires exactly: {', '.join(sorted(keys))}")


def string(value: Any, label: str, *, limit: int = 12000, empty: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()) or "\x00" in value:
        raise ProtocolError(f"{label} must be {'a' if empty else 'a nonempty'} string of at most {limit} characters without NUL")
    return value


def string_list(value: Any, label: str, *, max_items: int = 32) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise ProtocolError(f"{label} must be a list of at most {max_items} strings")
    return [string(x, label, limit=2000) for x in value]


def parse_action(text: str, max_duration: float = 120) -> dict[str, Any]:
    data = parse_object(text)
    exact_keys(data, {"analysis", "operation", "keystrokes", "duration", "goal_id", "final_answer"}, "action")
    for name in ("analysis", "keystrokes", "goal_id", "final_answer"):
        string(data[name], name, empty=True)
    if data["operation"] not in {"execute", "verify", "finish", "stop"}:
        raise ProtocolError("operation must be execute, verify, finish, or stop")
    value = data["duration"]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= max_duration or not math.isfinite(value):
        raise ProtocolError("duration outside allowed finite range")
    if data["operation"] == "verify":
        if not data["goal_id"] or data["keystrokes"]:
            raise ProtocolError("verify needs an existing goal_id and empty keystrokes")
    elif data["goal_id"]:
        raise ProtocolError("Only verify may specify goal_id")
    if data["operation"] in {"finish", "stop"} and data["keystrokes"]:
        raise ProtocolError("finish/stop cannot execute keystrokes")
    return data
