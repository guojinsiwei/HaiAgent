"""Small, task-local memory grounded in command observations, not model claims.

Unknown dependencies never justify skipping a tool.  Test outcomes use a whole
workspace dependency: a previous pass is stale after *any* source change.  Read
reuse is deliberately narrower and is only possible for explicit regular files.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

from .models import CommandResult, CommandSpec, EnvironmentSnapshot, ExecutionOutcome, MacroAction


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _clip(text: str, length: int) -> str:
    return text if len(text) <= length else text[:max(0, length - 18)] + "…[excerpt clipped]"


def _excerpt(result: CommandResult, length: int = 900) -> str:
    """Prefer actual error lines; keep the tail where test summaries usually live."""
    text = result.stderr.strip() or result.stdout.strip()
    if len(text) <= length:
        return text
    lines = text.splitlines()
    errors = [line for line in lines if re.search(r"(?i)error|fail|exception|assert|traceback", line)]
    important = "\n".join(errors[-5:])
    if important:
        return _clip(important, length // 2) + "\n…[tail]\n" + text[-length // 2:]
    return "…[tail]\n" + text[-max(0, length - 12):]


@dataclass
class _Read:
    key: str
    files: dict[str, str]
    executable: str
    environment: str


class EvidenceMemory:
    """One instance per task. It neither executes tools nor changes a workspace.

    ``check_command`` returns an explicitly marked *past observation*, not a new
    tool execution. Callers must separately count cache retrievals, never count
    them as successful newly executed tools or official task success.
    """

    def __init__(self, seed_workspace: Path, *, max_records: int = 256, max_cached_reads: int = 128):
        self.seed_workspace = Path(seed_workspace).resolve()
        self.max_records = max(8, max_records)
        self.max_cached_reads = max(1, max_cached_reads)
        self._aliases = {str(self.seed_workspace), self.seed_workspace.as_posix()}
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._cache: OrderedDict[str, tuple[_Read, dict[str, Any]]] = OrderedDict()
        self._obligations: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._recent_hits: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._clock = 0
        self.metrics: dict[str, int] = {
            "observed_commands": 0, "cache_lookups": 0, "cache_hits": 0,
            "cache_invalidations": 0, "context_calls": 0,
            "rendered_obligations": 0, "rendered_observations": 0,
            "rendered_cached_reads": 0, "context_characters": 0,
            "evicted_observations": 0, "verification_obligation_overflow": 0,
        }

    def _register(self, snapshot: EnvironmentSnapshot) -> None:
        path = Path(snapshot.location).resolve()
        self._aliases.update((str(path), path.as_posix()))

    def _logical_text(self, text: str) -> str:
        for alias in sorted(self._aliases, key=len, reverse=True):
            text = re.sub(re.escape(alias) + r"(?=$|[\\/\"'\s\),;:\]])", "<workspace>", text)
        return text.replace("<workspace>\\", "<workspace>/")

    def _command(self, command: CommandSpec) -> dict[str, Any]:
        return {"argv": [self._logical_text(item) for item in command.argv],
                "cwd": self._logical_text(command.cwd), "stdin": self._logical_text(command.stdin) if command.stdin else command.stdin}

    def _path(self, value: str, snapshot: EnvironmentSnapshot, cwd: Path | None = None) -> Path | None:
        root = Path(snapshot.location).resolve()
        logical = self._logical_text(value)
        if logical == "<workspace>":
            path = root
        elif logical.startswith(("<workspace>/", "<workspace>\\")):
            path = root / logical[len("<workspace>") + 1:]
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
            resolved = path.resolve()
            resolved.relative_to(root)
            return resolved
        except (OSError, ValueError):
            return None

    @staticmethod
    def _file_hash(path: Path) -> str | None:
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size > 16 * 1024 * 1024:
                return None
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _read(self, command: CommandSpec, snapshot: EnvironmentSnapshot) -> _Read | None:
        """Whitelist, never guess shell semantics or Python side effects."""
        if not command.argv:
            return None
        tool = Path(command.argv[0]).name.lower().removesuffix(".exe")
        if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", tool):
            return self._python_read(command, snapshot)
        if command.stdin is not None:
            return None
        if tool not in {"cat", "head", "tail", "rg"}:
            return None
        root = Path(snapshot.location).resolve()
        cwd = self._path(command.cwd, snapshot)
        if cwd is None or not cwd.is_dir():
            return None
        argv = list(command.argv)
        indexes: list[int] = []
        pattern_seen = tool != "rg"
        end_options = False
        i = 1
        while i < len(argv):
            token = argv[i]
            if token == "--" and not end_options:
                end_options = True
                i += 1
                continue
            if not end_options and token.startswith("-"):
                if tool == "cat" and token in {"-n", "-b", "-s", "-E", "-T", "-v", "-A", "-e", "-t"}:
                    i += 1
                    continue
                if tool in {"head", "tail"}:
                    if token in {"-n", "--lines", "-c", "--bytes"} and i + 1 < len(argv) and re.fullmatch(r"[+-]?\d+", argv[i + 1]):
                        i += 2
                        continue
                    if re.fullmatch(r"(?:-[nc]?\d+|--(?:lines|bytes)=[+-]?\d+)", token) or token in {"-q", "--quiet", "--silent"}:
                        i += 1
                        continue
                if tool == "rg":
                    allowed = {"--no-config", "-n", "--line-number", "-F", "--fixed-strings", "-i", "--ignore-case", "-s", "--case-sensitive", "-w", "--word-regexp", "-x", "--line-regexp", "-v", "--invert-match", "-l", "--files-with-matches", "--files-without-match", "-c", "--count", "--count-matches", "-o", "--only-matching", "-H", "--with-filename", "--no-heading", "--heading", "--color=never", "--text", "-a"}
                    if token in allowed:
                        i += 1
                        continue
                    if token in {"-e", "--regexp"} and i + 1 < len(argv):
                        pattern_seen = True
                        i += 2
                        continue
                    if token in {"-m", "--max-count", "-A", "-B", "-C", "--after-context", "--before-context", "--context"} and i + 1 < len(argv) and argv[i + 1].isdigit():
                        i += 2
                        continue
                return None
            if not pattern_seen:
                pattern_seen = True
            else:
                indexes.append(i)
            i += 1
        if not indexes or len(indexes) > 16 or (tool in {"head", "tail"} and len(indexes) != 1):
            return None
        if tool == "rg" and os.environ.get("RIPGREP_CONFIG_PATH") and "--no-config" not in argv:
            return None
        files: dict[str, str] = {}
        canonical = list(argv)
        for index in indexes:
            if argv[index] == "-":
                return None
            path = self._path(argv[index], snapshot, cwd)
            signature = self._file_hash(path) if path else None
            if signature is None:
                return None  # Directories, FIFOs, missing paths, and symlinks are unknown.
            relative = path.relative_to(root).as_posix()
            files[relative] = signature
            canonical[index] = "<workspace>/" + relative
        canonical[0] = tool
        return self._finish_read(command, cwd.relative_to(root).as_posix(), canonical, files)

    def _finish_read(self, command: CommandSpec, cwd: str, canonical: Any, files: dict[str, str]) -> _Read | None:
        executable_path = shutil.which(command.argv[0])
        if not executable_path:
            return None
        executable_hash = self._file_hash(Path(executable_path).resolve())
        if executable_hash is None:
            return None
        executable = _digest([str(Path(executable_path).resolve()), executable_hash])
        key = _digest([canonical, cwd])
        # Store only a digest; environment variables (including credentials) are
        # never exposed in prompts, reports or logs.
        environment = _digest(sorted(os.environ.items()))
        return _Read(key, files, executable, environment)

    def _python_read(self, command: CommandSpec, snapshot: EnvironmentSnapshot) -> _Read | None:
        """A tiny AST language for printing literal Path reads, never ``eval``.

        Supports explicit pathlib imports, simple local assignments, literal
        encodings, literal slices, splitlines and literal-separator join. All
        other calls, imports, attributes, loops, comprehensions, operators and
        dynamic paths are unknown. The source itself is never executed here.
        """
        if len(command.argv) == 3 and command.argv[1] == "-c" and command.stdin is None:
            source = command.argv[2]
            mode = "-c"
        elif command.argv[1:] == ("-",) and command.stdin is not None:
            source = command.stdin
            mode = "-"
        else:
            return None
        if len(source) > 32_000:
            return None
        cwd = self._path(command.cwd, snapshot)
        if cwd is None or not cwd.is_dir():
            return None
        root = Path(snapshot.location).resolve()
        # A task-local pathlib or Python startup hook can turn an apparently
        # read-only script into arbitrary code. Refuse caching in that case.
        search_roots = {root, cwd, root / "src", root / "lib"}
        for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep):
            if entry:
                mapped = self._path(entry, snapshot)
                search_roots.add(mapped if mapped is not None else Path(entry))
        if any((location / (name + ".py")).exists() or (location / name).exists()
               for location in search_roots for name in ("pathlib", "sitecustomize", "usercustomize")):
            return None
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            return None
        bindings: dict[str, tuple[str, Any]] = {}
        files: dict[str, str] = {}
        printed = False

        def literal(node: ast.AST) -> Any:
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, bool, type(None))):
                return node.value
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)) and isinstance(node.operand, ast.Constant) and type(node.operand.value) is int:
                return node.operand.value * (-1 if isinstance(node.op, ast.USub) else 1)
            raise ValueError("nonliteral")

        def expression(node: ast.AST) -> tuple[str, Any]:
            if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes, int, bool, type(None))):
                return "literal", node.value
            if isinstance(node, ast.Name) and node.id in bindings:
                return bindings[node.id]
            if isinstance(node, ast.Subscript):
                kind, value = expression(node.value)
                if kind not in {"text", "bytes", "lines"}:
                    raise ValueError("not a read")
                if isinstance(node.slice, ast.Slice):
                    for part in (node.slice.lower, node.slice.upper, node.slice.step):
                        if part is not None and type(literal(part)) is not int:
                            raise ValueError("nonliteral slice")
                    if node.slice.step is not None and literal(node.slice.step) == 0:
                        raise ValueError("zero step")
                elif type(literal(node.slice)) is not int:
                    raise ValueError("nonliteral index")
                return ("text" if kind == "lines" and not isinstance(node.slice, ast.Slice) else kind), value
            if not isinstance(node, ast.Call):
                raise ValueError("unknown expression")
            function = node.func
            constructor = (isinstance(function, ast.Name) and bindings.get(function.id) == ("constructor", "Path"))
            constructor = constructor or (isinstance(function, ast.Attribute) and function.attr == "Path" and isinstance(function.value, ast.Name) and bindings.get(function.value.id) == ("module", "pathlib"))
            if constructor:
                if len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    raise ValueError("dynamic path")
                path = self._path(node.args[0].value, snapshot, cwd)
                signature = self._file_hash(path) if path else None
                if signature is None:
                    raise ValueError("unknown file dependency")
                relative = path.relative_to(root).as_posix()
                # Canonicalize the literal path alone, not arbitrary strings
                # whose literal value may be part of printed output.
                node.args[0].value = "<workspace>/" + relative
                return "path", (relative, signature)
            if isinstance(function, ast.Attribute):
                kind, value = expression(function.value)
                if kind == "path" and function.attr in {"read_text", "read_bytes"}:
                    if function.attr == "read_bytes":
                        if node.args or node.keywords:
                            raise ValueError("read_bytes arguments")
                    else:
                        if len(node.args) > 2 or any(not isinstance(literal(arg), (str, type(None))) for arg in node.args):
                            raise ValueError("dynamic encoding")
                        if any(item.arg not in {"encoding", "errors"} or not isinstance(literal(item.value), (str, type(None))) for item in node.keywords):
                            raise ValueError("unknown read option")
                    files[value[0]] = value[1]
                    return ("text" if function.attr == "read_text" else "bytes"), value
                if kind == "text" and function.attr == "splitlines":
                    if len(node.args) > 1 or any(type(literal(arg)) is not bool for arg in node.args):
                        raise ValueError("splitlines option")
                    if any(item.arg != "keepends" or type(literal(item.value)) is not bool for item in node.keywords):
                        raise ValueError("splitlines option")
                    return "lines", value
                if kind == "literal" and isinstance(value, str) and function.attr == "join" and len(node.args) == 1 and not node.keywords:
                    child_kind, child_value = expression(node.args[0])
                    if child_kind == "lines":
                        return "text", child_value
            raise ValueError("unknown call")

        try:
            for statement in tree.body:
                if isinstance(statement, ast.Import) and len(statement.names) == 1 and statement.names[0].name == "pathlib":
                    name = statement.names[0].asname or "pathlib"
                    if name == "print" or name in bindings:
                        return None
                    bindings[name] = ("module", "pathlib")
                elif isinstance(statement, ast.ImportFrom) and statement.module == "pathlib" and statement.level == 0 and len(statement.names) == 1 and statement.names[0].name == "Path":
                    name = statement.names[0].asname or "Path"
                    if name == "print" or name in bindings:
                        return None
                    bindings[name] = ("constructor", "Path")
                elif isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
                    name = statement.targets[0].id
                    if name == "print" or (name in bindings and bindings[name][0] in {"constructor", "module"}):
                        return None
                    bindings[name] = expression(statement.value)
                elif isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call) and isinstance(statement.value.func, ast.Name) and statement.value.func.id == "print":
                    call = statement.value
                    if any(expression(arg)[0] not in {"text", "bytes", "lines", "literal"} for arg in call.args):
                        return None
                    if any(item.arg not in {"sep", "end"} or not isinstance(literal(item.value), str) for item in call.keywords):
                        return None
                    printed = True
                else:
                    return None
        except (ValueError, TypeError, RecursionError):
            return None
        if not printed or not files or len(files) > 16:
            return None
        canonical = ["python_read", mode, ast.dump(tree, include_attributes=False)]
        return self._finish_read(command, cwd.relative_to(root).as_posix(), canonical, files)

    @staticmethod
    def _is_check(command: CommandSpec) -> bool:
        if not command.argv:
            return False
        name = Path(command.argv[0]).name.casefold().removesuffix(".exe")
        if name in {"pytest", "py.test"}:
            return True
        if name.startswith("python"):
            args = command.argv[1:]
            return (len(args) > 1 and args[0] == "-m" and args[1] in {"pytest", "unittest"}) or any(Path(arg).name in {"runtests.py", "test.py"} for arg in args[:1]) or (len(args) > 1 and Path(args[0]).name == "manage.py" and args[1] == "test")
        return False

    def observe(self, action: MacroAction, outcome: ExecutionOutcome, before_snapshot: EnvironmentSnapshot) -> None:
        self._register(before_snapshot)
        self._register(outcome.resulting_snapshot)
        # Only a prefix consisting entirely of known pure reads has a known
        # pre-command state. Never cache a read after a write inside a batch.
        pure_prefix = True
        for index, result in enumerate(outcome.command_results):
            read = self._read(result.command, before_snapshot) if pure_prefix else None
            pure_prefix = pure_prefix and read is not None and not result.blocked and not result.timed_out
            # The executor reports a batch-final snapshot, not per-command
            # snapshots. A check before a later write cannot attest the final
            # workspace. Mark its dependency unknown rather than inventing it.
            last_command = index == len(outcome.command_results) - 1
            observation_snapshot = before_snapshot if read is not None else outcome.resulting_snapshot
            self._record(result, observation_snapshot, is_check=self._is_check(result.command),
                         state_known=read is not None or last_command)
            if read is not None and not result.output_truncated and not result.blocked and not result.timed_out and result.return_code in ({0, 1} if Path(result.command.argv[0]).name.removesuffix(".exe") == "rg" else {0}) and not result.stderr and len(result.stdout) <= 64_000:
                record_id = _digest(self._command(result.command))[:16]
                cached = {"cached": True, "evidence_id": record_id, "source_snapshot": outcome.resulting_snapshot.snapshot_id,
                          "return_code": result.return_code, "stdout": result.stdout, "stderr": result.stderr,
                          "argv": list(result.command.argv), "cwd": result.command.cwd,
                          "output_is_prior_observation": True, "dependencies": sorted(read.files)}
                self._cache[read.key] = (read, cached)
                self._cache.move_to_end(read.key)
                while len(self._cache) > self.max_cached_reads:
                    self._cache.popitem(last=False)
        for result in outcome.functional_validation_results:
            self._record(result, outcome.resulting_snapshot, is_check=True)
        for result in outcome.validation_results:
            self._record(result, outcome.resulting_snapshot, is_check=False)

    def _record(self, result: CommandResult, snapshot: EnvironmentSnapshot, *, is_check: bool, state_known: bool = True) -> None:
        self._clock += 1
        self.metrics["observed_commands"] += 1
        command = self._command(result.command)
        record_id = _digest(command)[:16]
        record = {"id": record_id, **command, "return_code": result.return_code,
                  "blocked": result.blocked, "timed_out": result.timed_out,
                  "output_truncated": result.output_truncated, "evidence": self._logical_text(_excerpt(result)),
                  "observed_fingerprint": snapshot.fingerprint if state_known else "unknown_intermediate_batch_state", "source_snapshot": snapshot.snapshot_id,
                  "sequence": self._clock, "kind": "public_check" if is_check else "command_observation"}
        self._records[record_id] = record
        self._records.move_to_end(record_id)
        while len(self._records) > self.max_records:
            self._records.popitem(last=False)
            self.metrics["evicted_observations"] += 1
        if is_check:
            # Exact original command stays available through verification_obligations;
            # context uses a bounded explicitly marked display, never runnable truncation.
            old = self._obligations.get(record_id)
            ever_failed = bool(old and old["ever_failed"]) or not result.succeeded
            self._obligations[record_id] = {**record, "command": result.command,
                                           "passed": result.succeeded, "ever_failed": ever_failed,
                                           "dependency_scope": "whole_workspace"}
            self._obligations.move_to_end(record_id)
            if len(self._obligations) > 128:
                disposable = next((key for key, item in self._obligations.items() if not item["ever_failed"]), None)
                if disposable:
                    self._obligations.pop(disposable)
                else:
                    # Do not silently forget failures. The usual tool budget is
                    # below this limit; overflow is explicit if callers exceed it.
                    self._obligations.popitem(last=False)
                    self.metrics["verification_obligation_overflow"] += 1

    def check_command(self, command: CommandSpec, snapshot: EnvironmentSnapshot) -> dict[str, Any] | None:
        self._register(snapshot)
        self.metrics["cache_lookups"] += 1
        read = self._read(command, snapshot)
        if read is None or read.key not in self._cache:
            return None
        previous, cached = self._cache[read.key]
        if (read.files, read.executable, read.environment) != (previous.files, previous.executable, previous.environment):
            self.metrics["cache_invalidations"] += 1
            return None
        self.metrics["cache_hits"] += 1
        result = {**cached, "requested_argv": list(command.argv), "requested_cwd": command.cwd}
        self._recent_hits[cached["evidence_id"]] = result
        self._recent_hits.move_to_end(cached["evidence_id"])
        while len(self._recent_hits) > 12:
            self._recent_hits.popitem(last=False)
        return result

    def verification_obligations(self, snapshot: EnvironmentSnapshot) -> list[dict[str, Any]]:
        """Exact command objects plus truthful current/stale outcome labels.

        These are reminders, not mandatory auto-tests or proof of task success.
        A same-command later pass closes that failure only for its fingerprint.
        """
        self._register(snapshot)
        items = []
        for item in self._obligations.values():
            stale = item["observed_fingerprint"] != snapshot.fingerprint
            status = ("stale_" if stale else "") + ("passed" if item["passed"] else "failed")
            items.append({**item, "status": status, "stale": stale,
                          "needs_recheck": stale or not item["passed"]})
        return sorted(items, key=lambda item: (not item["needs_recheck"], item["passed"], -item["sequence"]))

    @staticmethod
    def _view(item: dict[str, Any], width: int = 480) -> dict[str, Any]:
        argv = item.get("argv", [])
        encoded = json.dumps(argv, ensure_ascii=False)
        command = {"argv": argv} if len(encoded) <= width else {"argv_excerpt": _clip(encoded, width), "command_truncated": True}
        view = {"id": item.get("id", item.get("evidence_id")), **command,
                "cwd": _clip(item.get("cwd", "."), 160), "return_code": item.get("return_code"),
                "evidence": _clip(item.get("evidence", item.get("stderr") or item.get("stdout", "")), width)}
        for name in ("status", "needs_recheck", "dependency_scope", "cached", "output_truncated", "kind", "source_snapshot"):
            if name in item:
                view[name] = item[name]
        if item.get("stdin"):
            view["stdin_excerpt"] = _clip(item["stdin"], 180)
        return view

    def context(self, snapshot: EnvironmentSnapshot, limit_chars: int = 6000) -> dict[str, Any]:
        self._register(snapshot)
        limit_chars = max(2, limit_chars)
        obligations = self.verification_obligations(snapshot)
        obligation_ids = {item["id"] for item in obligations}
        records = [{**item, "status": ("unknown_intermediate_state" if item["observed_fingerprint"] == "unknown_intermediate_batch_state" else
                                      "current_workspace_observation" if item["observed_fingerprint"] == snapshot.fingerprint else "stale_workspace_observation")}
                   for item in reversed(self._records.values()) if item["id"] not in obligation_ids]
        # Errors outrank recent successful reads; no model-authored conclusions.
        records.sort(key=lambda item: (item["return_code"] == 0, -item["sequence"]))
        payload: dict[str, Any] = {"policy": "Observed task-local evidence only. Old failures and stale passes are reminders, not proof of current failure or success. Unknown dependencies never forbid an action.",
                                   "obligations": [], "recent_evidence": [], "cached_reads": [],
                                   "omitted_records": len(obligations) + len(records) + len(self._recent_hits),
                                   "lost_obligations": self.metrics["verification_obligation_overflow"]}
        if len(json.dumps(payload, ensure_ascii=False)) > limit_chars:
            payload = {"omitted_records": len(obligations) + len(records) + len(self._recent_hits)}
            if len(json.dumps(payload)) > limit_chars:
                payload = {}
        else:
            previous_reads = [{**item, "status": "previously_reused_not_current_validation"} for item in reversed(self._recent_hits.values())]
            groups = (("obligations", obligations), ("cached_reads", previous_reads), ("recent_evidence", records))
            for group, items in groups:
                for item in items:
                    for width in (480, 240, 96):
                        view = self._view(item, width)
                        payload[group].append(view)
                        payload["omitted_records"] -= 1
                        if len(json.dumps(payload, ensure_ascii=False)) <= limit_chars:
                            break
                        payload[group].pop()
                        payload["omitted_records"] += 1
        self.metrics["context_calls"] += 1
        self.metrics["context_characters"] += len(json.dumps(payload, ensure_ascii=False))
        self.metrics["rendered_obligations"] += len(payload.get("obligations", []))
        self.metrics["rendered_cached_reads"] += len(payload.get("cached_reads", []))
        self.metrics["rendered_observations"] += len(payload.get("recent_evidence", []))
        return payload
