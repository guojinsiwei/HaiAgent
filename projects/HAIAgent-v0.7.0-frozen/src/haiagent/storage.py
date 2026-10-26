"""Fresh-run append-only accounting, bounded evidence, and atomic result writes."""
import hashlib
import json
import os
from pathlib import Path
import time
import uuid


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class Recorder:
    def __init__(self, directory, secrets=()):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=False)
        self.path = self.directory / "events.jsonl"
        self.path.touch(exist_ok=False)
        self.secrets = tuple(s for s in secrets if s)
        self.previous = "0" * 64
        self.sequence = 0

    def clean(self, value):
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.clean(v) for v in value]
        return value

    def emit(self, event, **fields):
        self.sequence += 1
        row = self.clean({"event": event, "sequence": self.sequence,
                          "time": time.time(), "previous": self.previous, **fields})
        row["sha256"] = digest(row)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical(row) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.previous = row["sha256"]
        return row

    def save(self, name, value):
        atomic_json(self.directory / name, self.clean(value))


def read_trace(path):
    rows, previous = [], "0" * 64
    for index, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        row = json.loads(line)
        signature = row.get("sha256")
        body = {k: v for k, v in row.items() if k != "sha256"}
        if row.get("sequence") != index or row.get("previous") != previous or digest(body) != signature:
            raise ValueError("Trace checksum/sequence mismatch; audit refused")
        rows.append(row)
        previous = signature
    if not rows or rows[0].get("event") != "header":
        raise ValueError("Missing trace header")
    return rows
