"""Offline compatibility checks for explicit model reasoning wrappers."""

import json

import pytest

from reflexion.protocol import ProtocolError, parse_action
from reflexion.response_text import ReasoningPrefixError, strip_reasoning_prefix


@pytest.mark.parametrize("prefix", ["", " ", "\n\t"])
def test_removes_only_a_leading_closed_reasoning_block(prefix):
    assert strip_reasoning_prefix(prefix + "<think>private draft\nchecking</think>\n\nvisible\n") == "visible\n"


def test_empty_reasoning_block_is_supported():
    assert strip_reasoning_prefix("<think></think>answer") == "answer"


@pytest.mark.parametrize(
    "text",
    [
        ' {"analysis":"literal <think> and </think> inside JSON"}\n',
        "an answer that mentions <think>draft</think>",
        "ordinary text </think> more text",
        "<THINK>noncanonical uppercase</THINK> answer",
        " \nunchanged whitespace\n",
    ],
)
def test_preserves_tags_and_whitespace_when_there_is_no_explicit_prefix(text):
    assert strip_reasoning_prefix(text) == text


@pytest.mark.parametrize("text", ["<think>", "  <think>incomplete", "<think>draft</THINK>"])
def test_unclosed_lowercase_prefix_is_rejected(text):
    with pytest.raises(ReasoningPrefixError, match="unclosed"):
        strip_reasoning_prefix(text)


def test_tag_literals_inside_visible_json_survive_prefix_normalization():
    data = {"analysis": "Inspect literal </think>", "commands": [], "task_complete": True, "final_answer": "<think>example</think>"}
    response = json.dumps(data)
    assert strip_reasoning_prefix("<think>private draft</think>\n" + response) == response


def test_engine_parses_wrapped_action_and_preserves_literal_command_tags():
    command = "printf '%s' '<think>example</think>'\n"
    response = json.dumps({"analysis": "Print the literal", "commands": [{"keystrokes": command, "duration": 0}], "task_complete": False, "final_answer": ""})
    action = parse_action("<think>MODEL_PRIVATE_DRAFT</think>\n" + response)
    assert action.commands[0].keystrokes == command
    assert action.analysis == "Print the literal"


def test_unclosed_prefix_uses_the_engine_protocol_retry_path():
    with pytest.raises(ProtocolError, match="unclosed"):
        parse_action("<think>truncated draft")
