"""Task-local command evidence with conservative, condition-aware interventions.

No learned labels certify correctness. Unknown commands remain soft guidance;
only unchanged, successful, directly observed read queries can be redundant.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Literal

from .models import CommandSpec, EnvironmentSnapshot, MacroAction, StructuredContext, stable_id
from .rules import TaskRule
from .micro_experience import MicroExperienceIndex


@dataclass(frozen=True, slots=True)
class FileDependency:
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ExperienceRecord:
    evidence_id: str
    task_id: str
    kind: Literal["observation", "hypothesis", "reusable_verifier"]
    source_channel: str
    iteration: int
    parent_node_id: str
    child_node_id: str
    semantic_direction_id: str
    semantic_direction_label: str
    command: CommandSpec | None
    command_signature: str
    canonical_argv: tuple[str, ...]
    canonical_cwd: str
    return_code: int | None
    status: str
    stdout: str
    stderr: str
    output_sha256: str
    file_dependencies: tuple[FileDependency, ...]
    environment_token: str
    fallback_snapshot: str
    dependency_status: str
    observed_snapshot_id: str
    hard_block_eligible: bool
    claim: str
    counterexample_guidance: str
    supporting_evidence_ids: tuple[str, ...] = ()
    verifier_method_dependencies: tuple[FileDependency, ...] = ()
    verifier_replay_eligible: bool = False
    output_truncated: bool = False
    source_index: int = 0


@dataclass(frozen=True, slots=True)
class ExperienceDecision:
    blocked: bool = False
    feedback: tuple[str, ...] = ()
    matched_ids: tuple[str, ...] = ()
    reason: str = "no_applicable_command_evidence"
    reusable_verifier_ids: tuple[str, ...] = ()
    invalidated_ids: tuple[str, ...] = ()
    micro_matches: tuple[dict, ...] = ()


_MAX_HASH_BYTES = 16 * 1024 * 1024
_MAX_OUTPUT_CHARS = 1200
_QUERY_NAMES = {"cat", "head", "tail", "wc", "sed", "rg"}
_ENVIRONMENT_ERRORS = (
    "command not found", "not recognized as", "no module named", "modulenotfounderror",
    "importerror", "filenotfounderror", "no such file", "permission denied",
    "connection refused", "network is unreachable", "timed out", "timeout",
    "verification modified candidate files",
)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _file_digest(path: Path, max_bytes: int = _MAX_HASH_BYTES) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
            return None
        digest = hashlib.sha256()
        remaining = max_bytes + 1
        with path.open("rb") as stream:
            while remaining and (block := stream.read(min(1024 * 1024, remaining))):
                digest.update(block)
                remaining -= len(block)
        if not remaining:
            return None
        return digest.hexdigest()
    except OSError:
        return None


def _local_path(root: Path, cwd: str, value: str) -> tuple[str, Path] | None:
    try:
        working = Path(cwd)
        working = working if working.is_absolute() else root / working
        path = Path(value)
        path = path if path.is_absolute() else working / path
        lexical = Path(os.path.abspath(path))
        relative = lexical.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                return None
        resolved = lexical.resolve()
        if not resolved.is_relative_to(root):
            return None
        return relative.as_posix(), resolved
    except (OSError, ValueError, RuntimeError):
        return None


def _canonical(command: CommandSpec, snapshot: EnvironmentSnapshot) -> tuple[tuple[str, ...], str, str]:
    root = Path(snapshot.location).resolve()
    cwd_info = _local_path(root, ".", command.cwd)
    cwd = cwd_info[0] if cwd_info is not None else command.cwd
    argv: list[str] = []
    for value in command.argv:
        if Path(value).is_absolute():
            local = _local_path(root, command.cwd, value)
            if local is not None:
                value = "@workspace/" + local[0]
        argv.append(value)
    canonical_argv = tuple(argv)
    signature = _digest({"argv": canonical_argv, "cwd": cwd, "stdin": command.stdin})
    return canonical_argv, cwd, signature


def _command_name(command: CommandSpec) -> str:
    return Path(command.argv[0]).name.casefold().removesuffix(".exe") if command.argv else ""


def _environment_token(command: CommandSpec, snapshot: EnvironmentSnapshot, cache=None) -> tuple[str, bool]:
    root = Path(snapshot.location).resolve()
    cwd_info = _local_path(root, ".", command.cwd)
    executable = command.argv[0] if command.argv else ""
    explicit_executable = Path(executable).is_absolute() or "/" in executable or "\\" in executable
    path_known = explicit_executable or all(
        bool(entry) and Path(entry).is_absolute() for entry in os.environ.get("PATH", "").split(os.pathsep)
    )
    try:
        selected = shutil.which(executable)
        if Path(executable).is_absolute():
            selected = executable
        elif "/" in executable or "\\" in executable:
            info = _local_path(root, command.cwd, executable)
            selected = str(info[1]) if info is not None else None
        binary = Path(selected).resolve() if selected else None
    except (OSError, ValueError, RuntimeError):
        binary = None
    environment_hash = _digest(dict(os.environ))
    key = (str(binary), cwd_info[0] if cwd_info else command.cwd, str(root), environment_hash)
    # The caller creates a new cache per synchronous inspection. Nothing is
    # cached across actions, snapshots, or later reads of mutable file content.
    if cache is not None and key in cache:
        return cache[key]
    # Conda Linux Python is commonly larger than the bounded task-file limit.
    # This only broadens executable fingerprinting, not query dependency scope.
    binary_hash = _file_digest(binary, max_bytes=256 * 1024 * 1024) if binary is not None else None
    known = bool(path_known and binary_hash and cwd_info and cwd_info[1].is_dir()
                 and binary is not None and not binary.is_relative_to(root))
    # Store hashes, never environment values (which may contain credentials).
    token = _digest({"executable": str(binary), "binary_hash": binary_hash,
                     "cwd": cwd_info[0] if cwd_info else command.cwd,
                     "environment_hash": environment_hash})
    if cache is not None:
        cache[key] = (token, known)
    return token, known


def _query_files(command: CommandSpec) -> tuple[str, ...] | None:
    """An intentionally small grammar; never infer read-only behavior from prose."""
    name = _command_name(command)
    if name not in _QUERY_NAMES or command.stdin is not None:
        return None
    args = list(command.argv[1:])
    if name == "sed":
        if len(args) < 3 or args[0] != "-n" or not re.fullmatch(r"\d+(?:,(?:\d+|\$))?p", args[1]):
            return None
        args = args[2:]
    elif name in {"head", "tail"}:
        if args and args[0] in {"-n", "-c"}:
            if len(args) < 3 or not args[1].isdigit():
                return None
            args = args[2:]
    elif name == "wc":
        while args and re.fullmatch(r"-[lwcmL]+", args[0]):
            args.pop(0)
    elif name == "rg":
        if os.environ.get("RIPGREP_CONFIG_PATH") and "--no-config" not in args:
            return None
        switches = {"-n", "--line-number", "-i", "--ignore-case", "-F", "--fixed-strings",
                    "-w", "--word-regexp", "-x", "--line-regexp", "-s", "--case-sensitive",
                    "--no-heading", "-H", "--with-filename", "--no-filename", "-a", "--text",
                    "-c", "--count", "--count-matches", "-o", "--only-matching", "--no-config"}
        pattern = None
        while args:
            value = args[0]
            if value == "--":
                args.pop(0)
                break
            if value in switches:
                args.pop(0)
            elif value in {"-A", "-B", "-C", "-m", "--max-count"}:
                if len(args) < 2 or not args[1].isdigit():
                    return None
                args = args[2:]
            elif value == "-e":
                if len(args) < 2 or pattern is not None:
                    return None
                pattern = args[1]
                args = args[2:]
            elif value.startswith("-"):
                return None
            else:
                break
        if pattern is None:
            if not args:
                return None
            args.pop(0)
    if args and args[0] == "--":
        args.pop(0)
    if not args or any(not item or item.startswith("-") for item in args):
        return None
    return tuple(args)


def _dependencies(command: CommandSpec, snapshot: EnvironmentSnapshot, paths: tuple[str, ...] | None):
    root = Path(snapshot.location).resolve()
    selected: list[FileDependency] = []
    if paths is None:
        return (), False
    for value in paths:
        local = _local_path(root, command.cwd, value)
        if local is None:
            return tuple(selected), False
        digest = _file_digest(local[1])
        if digest is None:
            return tuple(selected), False
        selected.append(FileDependency(local[0], digest))
    return tuple(dict.fromkeys(selected)), bool(selected)


def _verifier_files(command: CommandSpec) -> tuple[str, ...] | None:
    name = _command_name(command)
    args = list(command.argv[1:])
    if command.stdin is not None:
        return None
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", name):
        if len(args) >= 3 and args[:2] == ["-m", "pytest"]:
            args = args[2:]
        elif len(args) == 1 and args[0].endswith(".py"):
            return (args[0],)
        else:
            return None
    elif name not in {"pytest", "py.test"}:
        return None
    files: list[str] = []
    for value in args:
        if value in {"-q", "-v", "-vv", "-x", "--disable-warnings", "--no-header", "--no-summary"}:
            continue
        path = value.split("::", 1)[0]
        if value.startswith("-") or not path.endswith(".py"):
            return None
        files.append(path)
    return tuple(files) or None


def _result_status(result) -> str:
    if result.blocked:
        return "blocked"
    if result.timed_out:
        return "timeout"
    return "succeeded" if result.return_code == 0 else "failed"


@dataclass
class TaskExperienceStore:
    task_id: str
    _records: list[ExperienceRecord] = field(default_factory=list, init=False)
    _seen: set[str] = field(default_factory=set, init=False)
    _events: dict[str, set[str]] = field(default_factory=dict, init=False)
    _by_id: dict[str, ExperienceRecord] = field(default_factory=dict, init=False)
    _by_signature: dict[str, list[ExperienceRecord]] = field(default_factory=dict, init=False)
    _micro: MicroExperienceIndex = field(init=False)

    def __post_init__(self) -> None:
        self._micro = MicroExperienceIndex(self.task_id)

    def _event(self, name: str, *key) -> None:
        self._events.setdefault(name, set()).add(_digest(key))

    def observe(self, transition) -> tuple[ExperienceRecord, ...]:
        if transition.task_id != self.task_id:
            raise ValueError("task experience scope violation")
        outcome = transition.outcome
        snapshot = outcome.resulting_snapshot
        action = transition.action
        all_reads = bool(action.commands) and all(_query_files(command) is not None for command in action.commands)
        stable_macro = all_reads and not outcome.workspace_changed and len(outcome.command_results) == len(action.commands)
        created: list[ExperienceRecord] = []
        token_cache = {}
        channels = (("command", outcome.command_results), ("automatic_validation", outcome.validation_results),
                    ("functional_validation", outcome.functional_validation_results))
        for channel, results in channels:
            for index, result in enumerate(results):
                command = result.command
                canonical_argv, cwd, signature = _canonical(command, snapshot)
                token, environment_known = _environment_token(command, snapshot, token_cache)
                dependencies, known = _dependencies(command, snapshot, _query_files(command))
                prior_dependencies, prior_known = _dependencies(command, outcome.parent_snapshot, _query_files(command))
                known = known and environment_known and prior_known and prior_dependencies == dependencies
                status = _result_status(result)
                public_verifier = channel == "functional_validation" and command in action.verification_commands
                method_deps, method_known = _dependencies(command, snapshot, _verifier_files(command))
                environment_error = any(marker in (result.stdout + "\n" + result.stderr).casefold() for marker in _ENVIRONMENT_ERRORS)
                replay_eligible = public_verifier and method_known and environment_known and status == "failed" and not environment_error
                kind = "reusable_verifier" if public_verifier else "observation"
                truncated = bool(getattr(result, "output_truncated", False)
                                 or len(result.stdout) > _MAX_OUTPUT_CHARS or len(result.stderr) > _MAX_OUTPUT_CHARS)
                hard = bool(channel == "command" and stable_macro and known and status == "succeeded"
                            and not action.verification_commands and not action.submit and not truncated)
                evidence_id = stable_id("evidence", {"task": self.task_id, "parent": transition.parent_node_id,
                    "child": transition.child_node_id, "iteration": transition.iteration, "channel": channel, "index": index,
                    "signature": signature, "output": _digest([result.return_code, result.stdout, result.stderr, status])})
                record = ExperienceRecord(
                    evidence_id, self.task_id, kind, channel, transition.iteration,
                    transition.parent_node_id, transition.child_node_id, action.semantic_direction_id,
                    action.semantic_direction_label, command, signature, canonical_argv, cwd,
                    result.return_code, status, result.stdout[:_MAX_OUTPUT_CHARS], result.stderr[:_MAX_OUTPUT_CHARS],
                    _digest([result.return_code, result.stdout, result.stderr, status]), dependencies, token,
                    snapshot.fingerprint, "known" if known else "unknown", snapshot.snapshot_id, hard,
                    f"Executed {channel} returned {result.return_code} ({status}); this is an observation, not proof of task completion.",
                    ("Replay the observed failing public check after a repair; also test a boundary or counterexample. Prior outcomes do not transfer."
                     if public_verifier else "If relevant files or execution conditions change, reread or reproduce before relying on this observation."),
                    (), method_deps, bool(replay_eligible), truncated, index,
                )
                if evidence_id in self._seen:
                    continue
                if status == "failed" and any(
                    earlier.status == "failed" and earlier.command_signature == signature
                    and earlier.environment_token == token and earlier.file_dependencies == dependencies
                    and (known and earlier.dependency_status == "known" or earlier.fallback_snapshot == snapshot.fingerprint)
                    for earlier in self._records
                ):
                    self._event("same_condition_failure_reobserved", evidence_id)
                self._seen.add(evidence_id)
                self._records.append(record)
                created.append(record)
                if self._has_conflict(record):
                    self._event("conflicting_same_condition_observations", evidence_id)
        old = set(transition.state_before.analysis_and_conclusions)
        hypotheses = [value for value in transition.state_after.analysis_and_conclusions if value not in old]
        if transition.assessment.feedback:
            hypotheses.append(transition.assessment.feedback)
        for text in tuple(dict.fromkeys(hypotheses))[:3]:
            evidence_id = stable_id("hypothesis", {"task": self.task_id, "iteration": transition.iteration,
                "child": transition.child_node_id, "text": text})
            if evidence_id in self._seen:
                continue
            record = ExperienceRecord(evidence_id, self.task_id, "hypothesis", "model_assessment", transition.iteration,
                transition.parent_node_id, transition.child_node_id, action.semantic_direction_id, action.semantic_direction_label,
                None, "", (), ".", None, "unverified", "", "", _digest(text), (), "", snapshot.fingerprint,
                "unknown", snapshot.snapshot_id, False, text[:1200],
                "This is a model interpretation. Check its premise against fresh command evidence and seek a counterexample.",
                tuple(item.evidence_id for item in created if item.kind != "hypothesis"))
            self._seen.add(evidence_id)
            self._records.append(record)
            created.append(record)
        if not created:
            return ()
        for record in created:
            self._by_id[record.evidence_id] = record
            if record.command_signature:
                self._by_signature.setdefault(record.command_signature, []).append(record)
            self._micro.add(record, transition)
        sources = {(record.source_channel, record.source_index): record for record in created
                   if record.kind != "hypothesis"}
        for hint in getattr(transition.assessment, "micro_experiences", ())[:3]:
            # Bind only to this transition's actual result. A model cannot name
            # another task, a future command, or a hallucinated evidence ID.
            source = sources.get((hint.source_channel, hint.source_index))
            if source is None or isinstance(hint.source_index, bool):
                self._event("micro_lessons_invalid_source", transition.iteration, repr(hint))
                continue
            self._micro.add_lesson(hint, source, snapshot)
        dropped = getattr(transition.assessment, "micro_experiences_dropped", 0)
        for index in range(dropped):
            self._event("micro_lessons_invalid_metadata", transition.iteration, transition.child_node_id, index)
        return tuple(created)

    def _rebind(self, record: ExperienceRecord, snapshot: EnvironmentSnapshot) -> CommandSpec | None:
        if record.command is None:
            return None
        root = Path(snapshot.location).resolve()
        argv = tuple(str(root / value.removeprefix("@workspace/")) if value.startswith("@workspace/") else value
                     for value in record.canonical_argv)
        return CommandSpec(argv, record.command.description, record.canonical_cwd,
                           record.command.timeout_seconds, record.command.stdin)

    def _has_conflict(self, record: ExperienceRecord) -> bool:
        return record.kind == "observation" and record.dependency_status == "known" and any(
            other.kind == "observation" and other.dependency_status == "known"
            and other.command_signature == record.command_signature
            and other.environment_token == record.environment_token
            and other.file_dependencies == record.file_dependencies
            and other.output_sha256 != record.output_sha256
            for other in self._records
        )

    def _validity(self, record: ExperienceRecord, snapshot: EnvironmentSnapshot, token_cache=None) -> str:
        command = self._rebind(record, snapshot)
        if command is None:
            return "unknown"
        token, _ = _environment_token(command, snapshot, token_cache)
        if token != record.environment_token:
            return "changed"
        if record.dependency_status != "known":
            return "changed" if snapshot.fingerprint != record.fallback_snapshot else "unknown"
        root = Path(snapshot.location).resolve()
        for dependency in record.file_dependencies:
            local = _local_path(root, ".", dependency.path)
            if local is None or _file_digest(local[1]) != dependency.sha256:
                return "changed"
        return "valid"

    def retrieve(self, *, context: StructuredContext, snapshot: EnvironmentSnapshot, limit: int) -> tuple[TaskRule, ...]:
        if limit <= 0:
            return ()
        token_cache = {}
        matches = self._micro.retrieve(
            context=context, snapshot=snapshot, limit=limit,
            validity_callback=lambda record, current: self._validity(record, current, token_cache),
        )
        projected = []
        for match in matches:
            entry = match.entry
            record = self._by_id[entry.representative_id]
            validity = match.source_validity
            conditional = entry.kind == "conditional_hypothesis"
            observed = f"{record.evidence_id}: {record.claim} output_sha256={record.output_sha256}"
            if record.command is not None:
                observed += f" argv={list(record.canonical_argv)!r} cwd={record.canonical_cwd!r}\nstdout={record.stdout}\nstderr={record.stderr}"
            if record.kind == "hypothesis":
                guidance = "Unverified hypothesis only: " + record.claim
            elif record.kind == "reusable_verifier":
                guidance = "Previously executed public check; rerun it on the current candidate. No prior pass/fail result is inherited. " + " ".join(record.canonical_argv)
            elif validity == "valid":
                guidance = "Reuse this command observation only while its recorded file and execution dependencies remain unchanged."
            else:
                guidance = "Conditions changed or are incomplete. Reread/reproduce; this record must not forbid an action."
            hard = record.hard_block_eligible and validity == "valid" and not self._has_conflict(record)
            if self._has_conflict(record):
                guidance = "Same recorded conditions produced conflicting outputs; dependencies may be incomplete. Rerun rather than hard-block."
            if record.output_truncated:
                guidance += " Stored output is truncated; repeat the read when complete evidence is needed."
            if conditional:
                hard = False
                guidance = ("Unverified conditional explanation, not a causal rule or a prohibition: "
                            + entry.lesson)
                if match.condition_status in {"changed", "declared_changed"}:
                    guidance += " A recorded premise changed; this is permission to reconsider, not proof the repair works."
                else:
                    guidance += " Check the matched premises; revise the premise or select a distinguishing public check."
            # All source IDs stay in the raw/index audit. Do not let a hundred
            # repeated observations consume the active prompt's token budget.
            source_ids = tuple(entry.source_ids[-3:])
            projected.append(TaskRule(
                rule_id=entry.micro_id if conditional else record.evidence_id, task_id=self.task_id,
                kind="avoid" if hard or record.status in {"failed", "timeout", "blocked"} else "recommend",
                semantic_direction_id=record.semantic_direction_id, action_name=entry.kind,
                evidence=(observed,), semantic_direction_label=record.semantic_direction_label,
                condition=f"dependency_status={validity}; files=" + ", ".join(item.path for item in record.file_dependencies)
                          + "; execution_token=" + record.environment_token[:16],
                guidance=guidance, scope="semantic_strategy", sharing_scope="task",
                evidence_ids=source_ids, experience_kind=entry.kind,
                condition_status=match.condition_status if conditional else validity,
                dependency_paths=tuple(item.path for item in record.file_dependencies), hard_block_eligible=hard,
                counterexample_guidance=entry.next_check or record.counterexample_guidance,
                micro_experience_id=entry.micro_id, source_count=len(entry.source_ids),
                operation=entry.operation, target_paths=tuple(entry.target_paths),
                premises=tuple(asdict(item) for item in match.premise_states),
                match_reasons=tuple(match.match_reasons), source_validity=validity,
            ))
        return tuple(projected)

    def evaluate(self, *, action: MacroAction, snapshot: EnvironmentSnapshot) -> ExperienceDecision:
        matched: list[str] = []
        invalidated: list[str] = []
        feedback: list[str] = []
        covered_commands = 0
        token_cache = {}
        for command in action.commands:
            _, _, signature = _canonical(command, snapshot)
            candidates = self._by_signature.get(signature, ())
            valid = []
            for record in candidates:
                validity = self._validity(record, snapshot, token_cache)
                matched.append(record.evidence_id)
                if record.hard_block_eligible and validity == "valid" and not self._has_conflict(record):
                    valid.append(record)
                elif record.hard_block_eligible and validity == "changed":
                    invalidated.append(record.evidence_id)
            if valid:
                covered_commands += 1
                record = valid[-1]
                # A veto carries the complete cached observation, even when the
                # record was not selected by Top-k prompt retrieval.
                feedback.append(f"{record.evidence_id}: unchanged read-query evidence; argv={list(record.canonical_argv)!r}; return_code={record.return_code}; stdout={record.stdout!r}; stderr={record.stderr!r}; output_sha256={record.output_sha256}. Reuse or change the information sought.")
        blocked = bool(action.commands and covered_commands == len(action.commands)
                       and not action.verification_commands and not action.submit
                       and all(_query_files(command) is not None for command in action.commands))
        if blocked:
            self._event("valid_duplicate_candidates", snapshot.snapshot_id, action.signature(), matched)
        elif invalidated:
            self._event("invalidated_retry_permissions", snapshot.snapshot_id, action.signature(), invalidated)
            feedback.append("Prior read evidence is stale under current dependencies; repeating the query is allowed.")
        verifiers = tuple(record.evidence_id for record in self._records
                          if record.kind == "reusable_verifier" and record.semantic_direction_id == action.semantic_direction_id)
        micro_matches = self._micro.match_action(
            action=action, snapshot=snapshot, limit=3,
            validity_callback=lambda record, current: self._validity(record, current, token_cache),
        )
        match_payloads = tuple(self._match_payload(item) for item in micro_matches)
        for match, payload in zip(micro_matches, match_payloads):
            matched.extend(match.entry.source_ids[-3:])
            matched.append(match.entry.micro_id)
            if match.entry.kind == "conditional_hypothesis":
                # Advisory matching never edits a command, upgrades a hypothesis
                # to a fact, awards priority, or blocks an uncertain action.
                feedback.append("Conditional experience match (advisory only): " + json.dumps(payload, ensure_ascii=False))
                self._event("conditional_action_matches", snapshot.snapshot_id, action.signature(),
                            match.entry.micro_id, match.condition_status)
        reason = "redundant_read_same_conditions" if blocked else "evidence_changed_retry_allowed" if invalidated else "soft_evidence_only" if matched else "no_applicable_command_evidence"
        return ExperienceDecision(blocked, tuple(feedback), tuple(dict.fromkeys(matched)), reason, verifiers,
                                  tuple(dict.fromkeys(invalidated)), match_payloads)

    @staticmethod
    def _match_payload(match) -> dict:
        entry = match.entry
        return {"micro_id": entry.micro_id, "kind": entry.kind,
                "source_ids": list(entry.source_ids[-3:]), "source_count": len(entry.source_ids),
                "operation": entry.operation, "target_paths": list(entry.target_paths),
                "condition_status": match.condition_status, "source_validity": match.source_validity,
                "premises": [asdict(item) for item in match.premise_states],
                "match_reasons": list(match.match_reasons), "lesson": entry.lesson,
                "next_check": entry.next_check, "hard_block_eligible": False,
                "causal_status": "not_established", "advice": (
                    "A premise changed: reconsider and verify the new attempt; do not inherit the old failure."
                    if match.condition_status in {"changed", "declared_changed"} else
                    "Check the premise, revise the operation or run a distinguishing public check within the existing budget.")}

    def verification_obligations(self, *, action: MacroAction, snapshot: EnvironmentSnapshot, limit: int = 1) -> tuple[CommandSpec, ...]:
        if limit <= 0:
            return ()
        referenced = set(action.applied_rule_ids) | set(action.avoided_rule_ids)
        selected: list[CommandSpec] = []
        signatures: set[str] = set()
        root = Path(snapshot.location).resolve()
        token_cache = {}
        for record in reversed(self._records):
            if not record.verifier_replay_eligible or not (
                record.semantic_direction_id == action.semantic_direction_id or record.evidence_id in referenced
            ):
                continue
            command = self._rebind(record, snapshot)
            if command is None or _environment_token(command, snapshot, token_cache)[0] != record.environment_token:
                continue
            if any((local := _local_path(root, ".", dependency.path)) is None
                   or _file_digest(local[1]) != dependency.sha256 for dependency in record.verifier_method_dependencies):
                continue
            if record.command_signature in signatures:
                continue
            signatures.add(record.command_signature)
            selected.append(command)
            self._event("public_failure_replay_obligations", snapshot.snapshot_id, record.evidence_id)
            if len(selected) >= limit:
                break
        return tuple(selected)

    def all(self) -> tuple[ExperienceRecord, ...]:
        return tuple(self._records)

    def report(self) -> dict:
        return {"record_count": len(self._records),
                "micro_index": self._micro.report(),
                "micro_experiences": [asdict(item) for item in self._micro.all()],
                "by_kind": {kind: sum(record.kind == kind for record in self._records)
                            for kind in ("observation", "hypothesis", "reusable_verifier")},
                "hard_block_eligible_records": sum(record.hard_block_eligible for record in self._records),
                **{name: len(self._events.get(name, ())) for name in (
                    "valid_duplicate_candidates", "invalidated_retry_permissions",
                    "same_condition_failure_reobserved", "public_failure_replay_obligations",
                    "conflicting_same_condition_observations", "micro_lessons_invalid_source",
                    "micro_lessons_invalid_metadata", "conditional_action_matches")},
                "failure_recurrence_is_causal": False,
                "failure_recurrence_scope": "Same recorded file/snapshot and execution tokens; unknown external state is not certified equal.",
                "false_block_rate": None,
                "false_block_rate_reason": "Requires counterfactual evaluation; not inferable from local logs."}
