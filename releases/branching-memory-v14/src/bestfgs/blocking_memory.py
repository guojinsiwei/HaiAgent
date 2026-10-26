"""Task-local, evidence-grounded blocking conditions with one-use leases.

This module does not execute commands. A failure produces a *hypothesis*, not a
causal claim. Only a generated, metered probe of a structurally necessary local
condition can postpone an exact command once. Neither model annotations nor
free-form error text can create a hard block. Generic failures remain advisory.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any
import uuid

from .models import CommandResult, CommandSpec, EnvironmentSnapshot, ExecutionOutcome, MacroAction


PROBE_MARKER = "BESTFGS_BLOCKING_PROBE_V12:"
_PYTHON = re.compile(r"python(?:\d+(?:\.\d+)*)?(?:\.exe)?$", re.I)
_IDENTIFIER = re.compile(r"[A-Za-z_]\w*$", re.ASCII)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _clip(text: str, length: int) -> str:
    return text if len(text) <= length else text[:max(0, length - 12)] + "...[clipped]"


class BlockingMemory:
    """One ledger per task; memory must never be shared between tasks.

    ``decide`` may return a read-only ``probe`` for the shared executor. The
    executor must charge it to normal tool budgets and call ``observe_probe``.
    A ``defer`` is not a tool execution or success. The controller must expose
    this event to the model and offer an explicit release override.
    """

    def __init__(self, seed_workspace: Path, *, max_records: int = 128,
                 max_probes_per_epoch: int = 2):
        self.seed_workspace = Path(seed_workspace).resolve()
        self.max_records = max(1, max_records)
        self.max_probes_per_epoch = min(2, max(0, max_probes_per_epoch))
        self._aliases = {str(self.seed_workspace), self.seed_workspace.as_posix()}
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._pending: dict[str, dict[str, Any]] = {}
        self._clock = 0
        self.metrics: dict[str, int] = {
            "observed_failures": 0, "records_created": 0, "records_evicted": 0,
            "probes_requested": 0, "probes_completed": 0, "probes_unknown": 0,
            "probe_budget_exhausted": 0, "deferred_actions": 0,
            "released_records": 0, "invalidated_records": 0,
            "override_releases": 0, "expired_leases": 0,
            "context_calls": 0, "rendered_records": 0,
        }

    def _register(self, snapshot: EnvironmentSnapshot) -> None:
        root = Path(snapshot.location).resolve()
        self._aliases.update((str(root), root.as_posix()))

    def _logical(self, text: str) -> str:
        for alias in sorted(self._aliases, key=len, reverse=True):
            text = re.sub(re.escape(alias) + r"(?=$|[\\/\"'\s\),;:\]])", "<workspace>", text)
        return text.replace("<workspace>\\", "<workspace>/")

    def _command(self, command: CommandSpec) -> dict[str, Any]:
        return {"argv": [self._logical(arg) for arg in command.argv],
                "cwd": self._logical(command.cwd),
                "stdin": self._logical(command.stdin) if command.stdin else command.stdin}

    def _path(self, value: str, snapshot: EnvironmentSnapshot,
              cwd: Path | None = None) -> Path | None:
        root = Path(snapshot.location).resolve()
        value = self._logical(value)
        if value == "<workspace>":
            path = root
        elif value.startswith(("<workspace>/", "<workspace>\\")):
            path = root / value[len("<workspace>") + 1:]
        else:
            path = Path(value)
            if not path.is_absolute():
                path = (cwd or root) / path
        try:
            relative = path.absolute().relative_to(root)
            current = root
            for part in relative.parts:
                current /= part
                if current.is_symlink():
                    return None
            path = path.resolve()
            path.relative_to(root)
            return path
        except (OSError, ValueError):
            return None

    def _runtime(self, argv: list[str], snapshot: EnvironmentSnapshot) -> tuple[str, Any]:
        executable = argv[0] if argv else ""
        if executable.startswith("<workspace>") or "/" in executable or "\\" in executable:
            path = self._path(executable, snapshot, self._path(".", snapshot))
            if path is None:
                path = Path(executable) if Path(executable).is_absolute() else None
        else:
            resolved = shutil.which(executable)
            path = Path(resolved) if resolved else None
        try:
            info = path.stat() if path else None
            return self._logical(str(path)), (info.st_size, info.st_mtime_ns, info.st_mode) if info else None
        except OSError:
            return self._logical(str(path)), None

    def _epoch(self, record: dict[str, Any], snapshot: EnvironmentSnapshot) -> str:
        condition = record["condition"]
        target = condition["target"]
        dependency: Any = None
        if condition["kind"] in {"cwd", "file"}:
            path = self._path(target, snapshot)
            try:
                info = path.stat() if path is not None else None
                # Existence is relevant even if a caller supplies an old snapshot
                # fingerprint after modifying the target in place.
                dependency = (info.st_mode, info.st_size, info.st_mtime_ns) if info else None
            except OSError:
                dependency = None
        environment = {name: self._logical(value) for name, value in os.environ.items()
                       if name != "RETRAC_WORKSPACE"}
        return _digest({"workspace": snapshot.fingerprint, "dependency": dependency,
                        "runtime": self._runtime(record["command"]["argv"], snapshot),
                        "environment": environment})

    def _invalidate_if_changed(self, record: dict[str, Any], snapshot: EnvironmentSnapshot) -> bool:
        epoch = self._epoch(record, snapshot)
        if epoch == record["epoch"]:
            return False
        record.update(state="stale", epoch=epoch, probe_count=0, remaining_defer_lease=0,
                      reason="Workspace, local dependency, runtime, or environment changed; retry is allowed.")
        self._pending.pop(record["blocker_id"], None)
        self.metrics["invalidated_records"] += 1
        return True

    def invalidate(self, reason: str = "Explicit workspace restoration") -> None:
        """Call after a restore even when restored contents have the same hash."""
        for record in self._records.values():
            record.update(state="stale", remaining_defer_lease=0, reason=reason)
            self.metrics["invalidated_records"] += 1
        self._pending.clear()

    def _condition(self, command: CommandSpec, result: CommandResult,
                   snapshot: EnvironmentSnapshot) -> dict[str, Any]:
        text = result.stderr + "\n" + result.stdout
        cwd = self._path(command.cwd, snapshot)
        if result.blocked and result.stderr.startswith("cwd escapes snapshot or is missing:") and cwd is not None:
            return {"kind": "cwd", "target": self._logical(str(cwd)), "structural": True,
                    "description": "The exact command requires an existing in-workspace working directory."}
        argv = command.argv
        if argv and result.return_code == 127 and re.search(r"\[Errno 2\]|\[WinError 2\]|No such file or directory", text, re.I):
            return {"kind": "executable", "target": self._logical(argv[0]), "structural": True,
                    "description": "The exact executable must be resolvable in this runtime and cwd."}
        python_args = list(argv[1:]) if argv and _PYTHON.fullmatch(Path(argv[0]).name) else []
        python_flags: list[str] = []
        # Only flags with no argument and no semantic ambiguity are recognized.
        while python_args and python_args[0] in {"-B", "-u", "-S", "-s", "-I", "-E", "-P"}:
            python_flags.append(python_args.pop(0))
        if python_args and not python_args[0].startswith("-") and cwd is not None:
            path = self._path(python_args[0], snapshot, cwd)
            if path is not None and re.search(r"can't open file|cannot open file", text, re.I) and re.search(r"Errno 2|No such file|cannot find", text, re.I):
                return {"kind": "file", "target": self._logical(str(path)), "structural": True,
                        "description": "Python requires this explicitly supplied script to exist."}
        missing = re.search(r"(?:ModuleNotFoundError:\s*)?No module named ['\"]?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", text)
        if missing:
            target = missing.group(1)
            direct = (len(python_args) >= 2 and python_args[0] == "-m"
                      and python_args[1] == target and bool(_IDENTIFIER.fullmatch(target))
                      and "-I" in python_flags and "-S" in python_flags)
            return {"kind": "module", "target": target, "structural": bool(direct),
                    "description": ("The directly launched isolated, no-site top-level Python module must be discoverable."
                                    if direct else "Missing import is a hypothesis only: site hooks or code can modify sys.path or synthesize modules.")}
        # Assertions, connection errors, tool permissions and arbitrary stderr
        # never turn into necessary conditions, even if repeatedly observed.
        return {"kind": "unknown", "target": "", "structural": False,
                "description": "Observed failure; its causal preconditions are not established."}

    def observe(self, action: MacroAction, outcome: ExecutionOutcome,
                before_snapshot: EnvironmentSnapshot) -> None:
        self._register(before_snapshot)
        self._register(outcome.resulting_snapshot)
        results = tuple(outcome.command_results) + tuple(outcome.functional_validation_results)
        for index, result in enumerate(results):
            key = _digest(self._command(result.command))
            existing = self._records.get(key)
            if result.succeeded:
                if existing:
                    existing.update(state="released", remaining_defer_lease=0,
                                    reason="The exact target command actually succeeded.")
                    existing["evidence"].append({"source": "target_execution", "return_code": 0,
                                                "snapshot": outcome.resulting_snapshot.snapshot_id})
                    existing["evidence"] = existing["evidence"][-8:]
                    self._pending.pop(existing["blocker_id"], None)
                    self.metrics["released_records"] += 1
                continue
            self.metrics["observed_failures"] += 1
            self._clock += 1
            # No truncated or timeout result may justify a concrete diagnosis.
            condition = ({"kind": "unknown", "target": "", "structural": False,
                          "description": "Incomplete observation; no blocking inference."}
                         if result.timed_out or result.output_truncated else
                         self._condition(result.command, result, before_snapshot))
            if existing is None:
                existing = {"blocker_id": "blocker_" + key[:16], "command": self._command(result.command),
                            "condition": condition, "state": "hypothesis", "evidence": [],
                            "epoch": "", "probe_count": 0, "remaining_defer_lease": 0,
                            "reason": "Failure observation is not proof of a necessary condition.", "occurrences": 0}
                self._records[key] = existing
                self.metrics["records_created"] += 1
            if existing["epoch"]:
                self._invalidate_if_changed(existing, before_snapshot)
            existing.update(condition=condition, state="hypothesis", remaining_defer_lease=0,
                            last_seen=self._clock, reason="Fresh target failure; a probe is required before any defer.")
            existing["epoch"] = self._epoch(existing, before_snapshot)
            existing["occurrences"] += 1
            existing["evidence"].append({"source": "target_execution", "return_code": result.return_code,
                                        "excerpt": _clip(result.stderr or result.stdout, 700),
                                        "snapshot": before_snapshot.snapshot_id if index == 0 else None,
                                        "state_scope": "before_first_command" if index == 0 else "unknown_within_batch",
                                        "timed_out": result.timed_out, "truncated": result.output_truncated})
            existing["evidence"] = existing["evidence"][-8:]
            self._pending.pop(existing["blocker_id"], None)
            self._records.move_to_end(key)
            while len(self._records) > self.max_records:
                _, evicted = self._records.popitem(last=False)
                self._pending.pop(evicted["blocker_id"], None)
                self.metrics["records_evicted"] += 1

    def _probe(self, record: dict[str, Any], command: CommandSpec,
               snapshot: EnvironmentSnapshot, nonce: str) -> CommandSpec | None:
        condition = record["condition"]
        kind = condition["kind"]
        payload = {"nonce": nonce, "kind": kind}
        header = "import json,os,sys,stat,shutil\n"
        body = "present=None\n"
        cwd = self._path(command.cwd, snapshot)
        if kind in {"cwd", "file"}:
            path = self._path(condition["target"], snapshot)
            if path is None:
                return None
            # Test absence only. Present directories supplied as scripts may be
            # executable packages, so file type is not guessed here.
            body += ("try:\n p=os.stat(" + repr(str(path)) + ")\n present="
                     + ("stat.S_ISDIR(p.st_mode)" if kind == "cwd" else "True")
                     + "\nexcept FileNotFoundError:\n present=False\nexcept OSError:\n pass\n")
            executable = (sys.executable, "-I", "-S", "-B")
            probe_cwd = "."
        elif kind == "executable":
            if cwd is None or not cwd.is_dir():
                return None
            target = condition["target"]
            if "/" in target or "\\" in target or target.startswith("<workspace>"):
                path = self._path(target, snapshot, cwd)
                if path is None:
                    # Never inspect arbitrary absolute paths supplied by a model.
                    return None
                target = str(path)
            body += "present=shutil.which(" + repr(target) + ") is not None\n"
            executable = (sys.executable, "-I", "-S", "-B")
            probe_cwd = command.cwd
        elif kind == "module":
            if (not condition["structural"] or not _IDENTIFIER.fullmatch(condition["target"])
                    or cwd is None or not cwd.is_dir()):
                return None
            if not command.argv or not _PYTHON.fullmatch(Path(command.argv[0]).name):
                return None
            # Never load task-local modules, sitecustomize or .pth startup code
            # just to diagnose an import. The top-level find_spec query neither
            # imports the target nor needs parent-package initialization. It is
            # equivalent only because the target was itself explicitly -I -S.
            body += ("import importlib.util\ntry:\n present=importlib.util.find_spec("
                     + repr(condition["target"]) + ") is not None\nexcept Exception:\n pass\n")
            executable = (command.argv[0], "-I", "-S", "-B")
            probe_cwd = command.cwd
        else:
            return None
        script = header + body + "payload=" + repr(payload) + "\npayload['present']=present\nprint(" + repr(PROBE_MARKER) + "+json.dumps(payload,sort_keys=True))\n"
        return CommandSpec((*executable, "-c", script), "Read-only blocking-condition diagnostic (metered)",
                           cwd=probe_cwd, timeout_seconds=10)

    def decide(self, command: CommandSpec, snapshot: EnvironmentSnapshot, *, turn: int) -> dict[str, Any]:
        self._register(snapshot)
        record = self._records.get(_digest(self._command(command)))
        if record is None:
            return {"kind": "allow", "reason": "No matching observed failure."}
        base = {"blocker_id": record["blocker_id"]}
        changed = self._invalidate_if_changed(record, snapshot)
        if changed or record["state"] in {"stale", "released", "unknown"}:
            return {**base, "kind": "allow", "reason": record["reason"]}
        if record["remaining_defer_lease"]:
            fresh = 0 <= turn - record.get("probe_turn", turn) <= 1
            record["remaining_defer_lease"] = 0
            if fresh:
                self.metrics["deferred_actions"] += 1
                return {**base, "kind": "defer", "reason": "Fresh diagnostic proved a necessary local condition absent; one postponement only. Change the condition, inspect evidence, or explicitly release this blocker."}
            self.metrics["expired_leases"] += 1
            record.update(state="stale", reason="Diagnostic lease expired; actual retry is allowed.")
            return {**base, "kind": "allow", "reason": record["reason"]}
        if record["state"] == "confirmed_blocked":
            return {**base, "kind": "allow", "reason": "The one-use postponement was consumed; do not permanently prohibit retries."}
        if record["condition"]["kind"] == "unknown":
            return {**base, "kind": "allow", "reason": "Failure cause remains unknown; never block on an assertion or generic connection error."}
        if record["probe_count"] >= self.max_probes_per_epoch:
            self.metrics["probe_budget_exhausted"] += 1
            return {**base, "kind": "allow", "reason": "Diagnostic budget for this unchanged state is exhausted; allow actual execution."}
        nonce = uuid.uuid4().hex
        probe = self._probe(record, command, snapshot, nonce)
        if probe is None:
            return {**base, "kind": "allow", "reason": "No safe generated diagnostic is available."}
        record["probe_count"] += 1
        self.metrics["probes_requested"] += 1
        self._pending[record["blocker_id"]] = {"nonce": nonce, "command": self._command(probe),
                                               "epoch": record["epoch"], "turn": turn}
        return {**base, "kind": "probe", "probe": probe,
                "reason": "Check the hypothesized condition with a read-only metered diagnostic before changing exploration."}

    def observe_probe(self, blocker_id: str, result: CommandResult,
                      snapshot: EnvironmentSnapshot, *, turn: int) -> None:
        self._register(snapshot)
        record = next((item for item in self._records.values() if item["blocker_id"] == blocker_id), None)
        pending = self._pending.pop(blocker_id, None)
        if record is None or pending is None:
            return
        self.metrics["probes_completed"] += 1
        if self._invalidate_if_changed(record, snapshot) or pending["epoch"] != record["epoch"]:
            self.metrics["probes_unknown"] += 1
            return
        valid = (result.succeeded and not result.output_truncated and not result.stderr.strip()
                 and self._command(result.command) == pending["command"] and turn == pending["turn"])
        value: bool | None = None
        if valid:
            lines = result.stdout.strip().splitlines()
            if len(lines) == 1 and lines[0].startswith(PROBE_MARKER):
                try:
                    parsed = json.loads(lines[0][len(PROBE_MARKER):])
                    if (type(parsed) is dict and set(parsed) == {"nonce", "kind", "present"}
                            and parsed["nonce"] == pending["nonce"]
                            and parsed["kind"] == record["condition"]["kind"]
                            and type(parsed["present"]) is bool):
                        value = parsed["present"]
                except (TypeError, ValueError):
                    pass
        record["evidence"].append({"source": "metered_generated_probe", "present": value,
                                    "return_code": result.return_code, "snapshot": snapshot.snapshot_id,
                                    "turn": turn, "epoch": record["epoch"]})
        record["evidence"] = record["evidence"][-8:]
        record["remaining_defer_lease"] = 0
        if value is None:
            record.update(state="unknown", reason="Diagnostic failed or could not establish the condition; actual retry remains allowed.")
            self.metrics["probes_unknown"] += 1
        elif value:
            record.update(state="released", reason="Diagnostic found the proposed prerequisite present; this does not prove target success.")
            self.metrics["released_records"] += 1
        elif record["condition"]["structural"]:
            record.update(state="confirmed_blocked", remaining_defer_lease=1, probe_turn=turn,
                          reason="Generated diagnostic observed a structurally necessary condition absent.")
        else:
            record.update(state="hypothesis", reason="Diagnostic supports a missing-condition hypothesis, but causal necessity is unproven; no hard block.")

    def release(self, blocker_id: str, reason: str = "Explicit model override") -> bool:
        record = next((item for item in self._records.values() if item["blocker_id"] == blocker_id), None)
        if record is None:
            return False
        record.update(state="released", remaining_defer_lease=0,
                      reason="Explicit override: " + _clip(reason, 300))
        self._pending.pop(blocker_id, None)
        self.metrics["override_releases"] += 1
        return True

    def has_blocker(self, blocker_id: str) -> bool:
        """Validate references without consuming leases or changing state."""
        return isinstance(blocker_id, str) and any(
            record["blocker_id"] == blocker_id for record in self._records.values())

    def context(self, snapshot: EnvironmentSnapshot, limit_chars: int = 4000) -> str:
        self._register(snapshot)
        self.metrics["context_calls"] += 1
        header = ("TASK-LOCAL BLOCKING EVIDENCE. Hypotheses are not causes. Confirmed local blockers "
                  "permit only one temporary postponement. Conditions may change; never treat these as task success.\n")
        if limit_chars <= len(header):
            return ""
        selected = []
        used = len(header)
        records = sorted(self._records.values(), key=lambda item: (
            item["state"] == "confirmed_blocked", item.get("last_seen", 0)), reverse=True)
        for record in records:
            self._invalidate_if_changed(record, snapshot)
            item = {"blocker_id": record["blocker_id"], "state": record["state"],
                    "command": record["command"], "condition": record["condition"],
                    "evidence": record["evidence"][-2:], "reason": record["reason"],
                    "remaining_defer_lease": record["remaining_defer_lease"]}
            # Clip values, never cut a condition or JSON record mid-structure.
            item["command"] = {"argv": [_clip(arg, 180) for arg in item["command"]["argv"][:12]],
                               "cwd": _clip(item["command"]["cwd"], 200)}
            line = json.dumps(item, ensure_ascii=False) + "\n"
            if used + len(line) > limit_chars:
                continue
            selected.append(line)
            used += len(line)
        self.metrics["rendered_records"] += len(selected)
        return header + "".join(selected) if selected else ""

    def report(self, snapshot: EnvironmentSnapshot) -> dict[str, Any]:
        self._register(snapshot)
        for record in self._records.values():
            self._invalidate_if_changed(record, snapshot)
        return {"version": "task-blocking-memory-v12", "scope": "task_local_only",
                "metrics": dict(self.metrics), "records": json.loads(json.dumps(list(self._records.values())))}
