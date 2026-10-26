"""Conservative command-aware output views; never rewrites or executes commands."""
from __future__ import annotations

from dataclasses import dataclass
import re
import shlex

from .types import TerminalEvent

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
DIAGNOSTIC = re.compile(
    r"error|fail|exception|traceback|assert|conflict|denied|refused|not found|"
    r"no such|warning|^E\s|^>\s|^[-+](?![-+])", re.I,
)
TEST_COUNT = re.compile(r"\b(\d+) (passed|failed|skipped|deselected|errors?|xfailed|xpassed)\b")
ERROR_SIGNATURE = re.compile(
    r"(?:ModuleNotFoundError|ImportError|TypeError|ValueError|AssertionError|"
    r"FileNotFoundError|PermissionError|RuntimeError):[^\n]*|"
    r"[^\n]*(?:Connection refused|command not found|No such file or directory)[^\n]*",
    re.I,
)


def clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    marker = "\n[excerpt clipped]\n"
    if limit <= len(marker):
        return marker[:limit]
    available = limit - len(marker)
    head = available * 2 // 3
    return text[:head] + marker + text[-(available - head):]


def command_type(command: str) -> str:
    try:
        # Treat shell operators/wrappers conservatively; quoted filenames stay intact.
        tokens = list(shlex.shlex(command, posix=True, punctuation_chars="|&;<>()"))
        args = shlex.split(command)
    except ValueError:
        return "generic"
    if not args or any(t and all(c in "|&;<>()" for c in t) for t in tokens):
        return "generic"
    executable = args[0].replace("\\", "/").rsplit("/", 1)[-1]
    if executable in {"sh", "bash", "zsh", "sudo", "env"}:
        return "generic"
    if executable == "pytest" or (
        re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
        and args[1:3] == ["-m", "pytest"]
    ):
        return "pytest"
    if executable in {"cargo", "go", "npm"} and args[1:2] == ["test"]:
        return "test"
    if executable in {"ls", "find", "tree"}:
        return "listing"
    if executable in {"rg", "grep"}:
        return "search"
    if executable in {"cat", "sed", "head", "tail"}:
        return "read"
    if executable == "git":
        return "git"
    if executable in {"pip", "pip3", "npm", "uv"}:
        return "install"
    if executable in {"make", "cmake", "gcc", "g++", "cargo", "ninja"}:
        return "build"
    return "generic"


@dataclass(frozen=True)
class Compressed:
    category: str
    output: str
    incomplete: bool
    reduced: bool
    error: str
    test_status: str | None
    test_summary: str


def compress(event: TerminalEvent, *, max_chars: int, scan_chars: int) -> Compressed:
    category = command_type(event.command)
    oversized = len(event.stdout) + len(event.stderr) > scan_chars
    if oversized:
        # Bound parsing work, with both streams represented; do not infer pass from a tail.
        raw = "[stdout]\n" + clip(event.stdout, scan_chars // 2)
        raw += "\n[stderr]\n" + clip(event.stderr, scan_chars // 2)
    else:
        raw = "[stdout]\n" + event.stdout + "\n[stderr]\n" + event.stderr
    text = ANSI.sub("", raw.replace("\r\n", "\n").replace("\r", "\n"))
    incomplete = event.output_truncated or oversized
    error_matches = list(ERROR_SIGNATURE.finditer(text))
    error = clip(error_matches[-1].group(0).strip(), 300) if error_matches else ""
    successful = event.exit_code == 0 and not event.timed_out and not event.blocked
    status = None
    summary = ""
    if category == "pytest":
        # Recognize footer syntax, not incidental mentions. Tool output remains untrusted.
        footers = [line.strip() for line in text.splitlines() if re.fullmatch(
            r"\s*=*\s*(?:\d+ (?:passed|failed|skipped|deselected|errors?|xfailed|xpassed)"
            r"(?:, \d+ (?:passed|failed|skipped|deselected|errors?|xfailed|xpassed|warnings?))*|no tests ran)"
            r" in \d+(?:\.\d+)?s(?: \([^\n]*\))?\s*=*\s*", line
        )]
        summary = clip(footers[-1], 400) if footers else "No recognized pytest summary."
        counts = {kind: int(count) for count, kind in TEST_COUNT.findall(summary)}
        if event.timed_out or event.blocked or incomplete or event.exit_code is None:
            status = "unverified"
        elif event.exit_code == 5 or "no tests ran" in summary.lower():
            status = "no_tests"
        elif not successful:
            status = "failed"
        elif counts.get("passed", 0) > 0 and not any(
            counts.get(k, 0) for k in ("failed", "error", "errors")
        ):
            status = "passed_scope_only"
        else:
            status = "unverified"
    lines = text.splitlines()
    if len(text) <= max_chars:
        output = text
    elif category in {"read", "git", "generic", "listing", "search"}:
        # Code/diffs/unknown output cannot safely be replaced with a semantic guess.
        output = clip(text, max_chars)
    else:
        keep: set[int] = set(range(min(3, len(lines))))
        keep.update(range(max(0, len(lines) - 8), len(lines)))
        for i, line in enumerate(lines):
            if DIAGNOSTIC.search(line):
                keep.update(range(max(0, i - 1), min(len(lines), i + 3)))
        selected = "\n".join(lines[i] for i in sorted(keep))
        output = clip("[filtered diagnostic excerpt]\n" + selected, max_chars)
    return Compressed(category, output, incomplete, output != text, error, status, summary)
