"""Adapters without importing frozen BestFGS releases or any model SDK."""
from __future__ import annotations

import hashlib
import shlex
from typing import Any

from .types import TerminalEvent


def from_command_result(task_id: str, result: Any, *, cwd: str,
                        workspace: str | None, environment: str | None) -> TerminalEvent:
    """Adapt BestFGS CommandResult; caller supplies actual resolved scope.

    Do not infer package/service state from the workspace hash. For command batches,
    supply the revisions for the individual command, not a guessed final-batch hash.
    """
    stdin = getattr(result.command, "stdin", None)
    return TerminalEvent(
        task_id=task_id, command=shlex.join(result.command.argv),
        stdout=result.stdout, stderr=result.stderr, exit_code=result.return_code,
        cwd=cwd, workspace=workspace, environment=environment,
        timed_out=getattr(result, "timed_out", False), blocked=getattr(result, "blocked", False),
        output_truncated=getattr(result, "output_truncated", False),
        input_digest=hashlib.sha256(stdin.encode()).hexdigest() if stdin is not None else "",
    )
