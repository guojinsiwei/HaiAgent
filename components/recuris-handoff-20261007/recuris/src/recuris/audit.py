"""Small JSON audit files with credential redaction.

The logger records supplied agent events, not model-provider headers. It is a
best-effort credential filter, not a general-purpose data anonymizer.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any, Iterable


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|auth(?:orization)?|password|passwd|secret|credential)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[^\s\"'<>]+", re.IGNORECASE)
_SK_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")
_ASSIGNMENT = re.compile(
    r"(?P<label>\b(?:[A-Z][A-Z0-9_]*_)?(?:API_KEY|ACCESS_TOKEN|SECRET|PASSWORD)"
    r"\s*[=:]\s*)(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)",
    re.IGNORECASE,
)
_MASK = "[REDACTED]"


def redact(value: Any, *, secrets: Iterable[str] = ()) -> Any:
    """Return a JSON-compatible value with common credential fields removed.

    Explicit secrets are always masked. Environment credentials are discovered
    by name and require eight characters to avoid replacing ordinary text when
    an unrelated variable has a short value. Sensitive mapping keys are masked
    regardless of their value's length.
    """
    known_secrets = {str(secret) for secret in secrets if secret}
    known_secrets.update(
        val
        for key, val in os.environ.items()
        if _SENSITIVE_KEY.search(key) and len(val) >= 8
    )
    ordered_secrets = sorted(known_secrets, key=len, reverse=True)

    def clean(item: Any) -> Any:
        if dataclasses.is_dataclass(item) and not isinstance(item, type):
            item = dataclasses.asdict(item)
        if isinstance(item, dict):
            return {
                str(key): _MASK if _SENSITIVE_KEY.search(str(key)) else clean(val)
                for key, val in item.items()
            }
        if isinstance(item, (list, tuple, set)):
            return [clean(val) for val in item]
        if item is None or isinstance(item, (bool, int, float)):
            return item
        if not isinstance(item, str):
            item = str(item)
        for secret in ordered_secrets:
            item = item.replace(secret, _MASK)
        item = _BEARER.sub("Bearer " + _MASK, item)
        item = _SK_KEY.sub(_MASK, item)
        return _ASSIGNMENT.sub(lambda match: match.group("label") + _MASK, item)

    return clean(value)


class JsonlLogger:
    """Write append-only events and atomic JSON snapshots to one directory."""

    def __init__(self, directory: Path | str, *, secrets: Iterable[str] = ()):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._secrets = tuple(secret for secret in secrets if secret)
        self._lock = threading.Lock()

    def write(self, event: str, **payload: Any) -> None:
        entry = dict(payload)
        entry.update(timestamp=datetime.now(timezone.utc).isoformat(), event=event)
        line = json.dumps(redact(entry, secrets=self._secrets), ensure_ascii=False, allow_nan=False)
        with self._lock:
            with (self.directory / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    def save(self, name: str, value: Any) -> Path:
        """Save a redacted JSON snapshot; ``.json`` is appended if omitted."""
        if not name or name in {".", ".."} or any(char in name for char in "/\\:"):
            raise ValueError("Snapshot name must be a simple file name")
        target = self.directory / (name if name.endswith(".json") else name + ".json")
        rendered = json.dumps(redact(value, secrets=self._secrets), ensure_ascii=False, indent=2, allow_nan=False)
        with self._lock:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".tmp", dir=self.directory, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(rendered + "\n")
            try:
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        return target
