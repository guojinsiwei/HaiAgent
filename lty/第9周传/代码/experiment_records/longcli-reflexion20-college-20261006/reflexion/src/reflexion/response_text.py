"""Normalize explicit reasoning wrappers at the assistant-text boundary.

This adapter deliberately accepts only the unambiguous lowercase
``<think>...</think>`` prefix. It does not split arbitrary task or JSON data
at a tag occurrence. Raw provider replies remain available to the audit log.
"""

from __future__ import annotations


class ReasoningPrefixError(ValueError):
    """An explicit leading reasoning wrapper is incomplete."""


def strip_reasoning_prefix(text: str) -> str:
    """Remove one closed, lowercase leading ``<think>`` block if present.

    Leading whitespace before the wrapper is accepted. If no wrapper occurs
    at the start, return the original text unchanged, including whitespace and
    literal tags. An unclosed wrapper is not treated as usable visible output.
    No recovery of a bare closing tag is attempted: its preceding text might
    be legitimate answer content rather than a reasoning prefix.
    """
    candidate = text.lstrip()
    if not candidate.startswith("<think>"):
        return text
    closing = candidate.find("</think>", len("<think>"))
    if closing < 0:
        raise ReasoningPrefixError("Leading <think> block is unclosed; return a complete visible response")
    return candidate[closing + len("</think>"):].lstrip()
