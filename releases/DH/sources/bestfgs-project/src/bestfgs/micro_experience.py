"""Task-local indexes over evidence, not a learned causal or blocking policy.

Raw command records remain owned by TaskExperienceStore. Aggregation preserves
every source ID; repeated observations are never independent confidence votes.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import time
from typing import Callable


_GENERIC = frozenset({"a", "an", "and", "are", "as", "at", "be", "by", "check", "cmd", "command",
    "do", "execute", "file", "files", "for", "from", "in", "is", "it", "of", "on", "or", "python",
    "python3", "read", "run", "sh", "bash", "test", "tests", "the", "this", "to", "with", "none"})
_FILE_PREDICATES = frozenset({"file_exists", "file_absent", "file_contains", "file_lacks"})
_SEMANTIC_PREDICATES = frozenset({"equals", "not_equals"})
_MAX_FILE_BYTES = 2 * 1024 * 1024


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _normalized(value: str) -> str:
    return " ".join(str(value).casefold().replace("_", " ").split())


def _tokens(value: str) -> set[str]:
    words = {item for item in re.findall(r"[a-z0-9]+", str(value).casefold()) if len(item) >= 3 and item not in _GENERIC}
    for run in re.findall(r"[\u3400-\u9fff]+", str(value)):
        words.update(run[i:i + 2] for i in range(len(run) - 1))
    return words


def _relative(value: str) -> str | None:
    """Lexically safe relative file names; no shell, glob or URI semantics."""
    if not isinstance(value, str) or not value or "\x00" in value or ":" in value:
        return None
    value = value.replace("\\", "/")
    if Path(value).is_absolute() or PureWindowsPath(value).is_absolute() or value.startswith("/"):
        return None
    parts = value.split("/")
    if any(part == ".." for part in parts) or any(char in value for char in "*?[]"):
        return None
    parts = [part for part in parts if part not in {"", "."}]
    return "/".join(parts) or None


def _is_redirect(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _safe_file(snapshot, subject: str) -> tuple[Path | None, str]:
    relative = _relative(subject)
    if relative is None:
        return None, "unsafe_or_nonrelative_path"
    try:
        root = Path(snapshot.location).absolute()
        if _is_redirect(root):
            return None, "workspace_is_redirected"
        root = root.resolve(strict=True)
        current = root
        for part in relative.split("/"):
            current = current / part
            try:
                if _is_redirect(current):
                    return None, "symlink_or_reparse_dependency"
            except FileNotFoundError:
                # A missing child is safe only after checking its existing ancestors.
                continue
        if not current.resolve(strict=False).is_relative_to(root):
            return None, "outside_workspace"
        return current, "safe_workspace_path"
    except (OSError, ValueError, RuntimeError):
        return None, "unreadable_workspace_path"


@dataclass(frozen=True, slots=True)
class PremiseState:
    subject: str
    predicate: str
    value: str
    status: str
    observed: str = ""
    reason: str = ""


@dataclass(frozen=True, slots=True)
class MicroEntry:
    micro_id: str
    task_id: str
    kind: str
    operation: str
    target_paths: tuple[str, ...]
    premises: tuple
    source_ids: tuple[str, ...]
    representative_id: str
    direction_ids: tuple[str, ...]
    command_signature: str
    observed_condition_key: str
    output_sha256: str
    lesson: str
    next_check: str
    trust: str
    source_evidence_usable: bool = True
    causal_status: str = "not_established"


@dataclass(frozen=True, slots=True)
class MicroMatch:
    entry: MicroEntry
    condition_status: str
    source_validity: str
    premise_states: tuple[PremiseState, ...]
    match_reasons: tuple[str, ...]
    hard_block_eligible: bool = False


def _file_premise(premise, snapshot, file_cache: dict, costs: dict) -> PremiseState:
    # Cache lifetime is exactly one retrieve/match_action call. A later call
    # must check even an identically named mutable snapshot from scratch.
    key = _relative(premise.subject) or premise.subject
    if key not in file_cache:
        path, reason = _safe_file(snapshot, premise.subject)
        state = {"path": path, "reason": reason}
        if path is not None:
            try:
                state.update(exists=path.exists(), regular=path.is_file())
            except OSError:
                state.update(path=None, reason="unreadable_or_non_utf8_file")
        file_cache[key] = state
    state = file_cache[key]
    path = state["path"]
    base = (premise.subject, premise.predicate, premise.value)
    if path is None:
        return PremiseState(*base, "unknown", reason=state["reason"])
    try:
        exists = state["exists"]
        if premise.predicate == "file_exists":
            return PremiseState(*base, "valid" if exists and state["regular"] else "changed", str(exists), "literal_file_existence")
        if premise.predicate == "file_absent":
            return PremiseState(*base, "valid" if not exists else "changed", str(exists), "literal_path_absence")
        if not exists or not state["regular"]:
            return PremiseState(*base, "unknown", "missing_or_nonregular", "cannot_read_required_file")
        if not premise.value:
            return PremiseState(*base, "unknown", reason="empty_literal_or_file_too_large")
        if "text" not in state and "content_error" not in state:
            if path.stat().st_size > _MAX_FILE_BYTES:
                state["content_error"] = "empty_literal_or_file_too_large"
            else:
                costs["file_read_operations"] += 1
                with path.open("rb") as stream:
                    data = stream.read(_MAX_FILE_BYTES + 1)
                costs["file_read_bytes"] += len(data)
                if len(data) > _MAX_FILE_BYTES:
                    state["content_error"] = "file_grew_beyond_read_limit"
                else:
                    state["text"] = data.decode("utf-8")
        if "content_error" in state:
            return PremiseState(*base, "unknown", reason=state["content_error"])
        contains = premise.value in state["text"]
        satisfied = contains if premise.predicate == "file_contains" else not contains
        return PremiseState(*base, "valid" if satisfied else "changed", f"contains_literal={contains}", "literal_utf8_content_check")
    except (OSError, UnicodeError):
        state["content_error"] = "unreadable_or_non_utf8_file"
        return PremiseState(*base, "unknown", reason="unreadable_or_non_utf8_file")


def _semantic_premise(premise, declarations: tuple) -> PremiseState:
    base = (premise.subject, premise.predicate, premise.value)
    related = [item for item in declarations if item.subject == premise.subject
               and item.predicate in _SEMANTIC_PREDICATES]
    states = []
    for item in related:
        same_value = item.value == premise.value
        if item.predicate == "equals":
            satisfied = same_value if premise.predicate == "equals" else not same_value
            states.append("declared_match" if satisfied else "declared_changed")
        elif same_value:
            states.append("declared_match" if premise.predicate == "not_equals" else "declared_changed")
    if not states or len(set(states)) != 1:
        return PremiseState(*base, "unknown", reason="no_decisive_or_consistent_action_declaration")
    return PremiseState(*base, states[0], "; ".join(f"{item.predicate}:{item.value}" for item in related),
                        "compared_with_action_declaration_only_not_environment_truth")


def _condition(states: tuple[PremiseState, ...], source_validity: str, conditional: bool) -> str:
    statuses = {item.status for item in states}
    if "changed" in statuses:
        return "changed"
    if "declared_changed" in statuses:
        return "declared_changed"
    if source_validity == "changed":
        return "changed"
    if "unknown" in statuses:
        return "unknown"
    if "declared_match" in statuses:
        return "declared_match"
    if conditional and not states:
        return "unknown"
    return source_validity if source_validity in {"valid", "changed"} else "unknown"


class MicroExperienceIndex:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self._entries: dict[str, MicroEntry] = {}
        self._sources: dict[str, object] = {}
        self._source_entries: dict[str, str] = {}
        self._operations: dict[str, set[str]] = defaultdict(set)
        self._files: dict[str, set[str]] = defaultdict(set)
        self._tokens: dict[str, set[str]] = defaultdict(set)
        self._entry_tokens: dict[str, set[str]] = defaultdict(set)
        self._directions: dict[str, set[str]] = defaultdict(set)
        self._commands: dict[str, set[str]] = defaultdict(set)
        self._verifiers: set[str] = set()
        self._rejected_lessons = 0
        self._condition_costs = {"premise_checks": 0, "file_read_operations": 0,
                                 "file_read_bytes": 0, "premise_check_seconds": 0.0}

    def _condition_key(self, record) -> str:
        dependencies = [(item.path, item.sha256) for item in record.file_dependencies]
        condition = {"dependencies": dependencies, "environment": record.environment_token,
                     "status": record.dependency_status}
        if record.dependency_status != "known":
            condition["snapshot"] = (record.observed_snapshot_id, record.fallback_snapshot)
        return _digest(condition)

    def _put(self, entry: MicroEntry, extra_tokens: str = "") -> MicroEntry:
        prior = self._entries.get(entry.micro_id)
        if prior is not None:
            entry = replace(entry, source_ids=tuple(dict.fromkeys((*prior.source_ids, *entry.source_ids))),
                            direction_ids=tuple(dict.fromkeys((*prior.direction_ids, *entry.direction_ids))),
                            target_paths=tuple(dict.fromkeys((*prior.target_paths, *entry.target_paths))))
        self._entries[entry.micro_id] = entry
        if entry.operation:
            self._operations[_normalized(entry.operation)].add(entry.micro_id)
        for target in entry.target_paths:
            self._files[target].add(entry.micro_id)
        for direction in entry.direction_ids:
            self._directions[direction].add(entry.micro_id)
        self._entry_tokens[entry.micro_id].update(_tokens(" ".join((entry.operation, *entry.target_paths, entry.lesson, entry.next_check, extra_tokens))))
        for token in self._entry_tokens[entry.micro_id]:
            self._tokens[token].add(entry.micro_id)
        if entry.command_signature:
            self._commands[entry.command_signature].add(entry.micro_id)
        if entry.kind == "reusable_verifier":
            self._verifiers.add(entry.micro_id)
        return entry

    def add(self, record, transition) -> MicroEntry:
        if record.task_id != self.task_id or transition.task_id != self.task_id:
            raise ValueError("task micro-experience scope violation")
        if record.evidence_id in self._source_entries:
            return self._entries[self._source_entries[record.evidence_id]]
        self._sources[record.evidence_id] = record
        condition_key = self._condition_key(record)
        key = (self.task_id, record.kind, record.source_channel, record.command_signature,
               condition_key, record.output_sha256, record.status, bool(record.output_truncated))
        if record.kind == "hypothesis":
            key += (record.claim,)
        micro_id = "micro-" + _digest(key)[:24]
        targets = tuple(dict.fromkeys(path for dependency in record.file_dependencies
                                     if (path := _relative(dependency.path)) is not None))
        targets += tuple(path for value in getattr(transition.action, "experience_targets", ())
                         if (path := _relative(value)) is not None and path not in targets)
        operation = ""
        if record.canonical_argv:
            name = Path(record.canonical_argv[0]).name.casefold().removesuffix(".exe")
            operation = name if name not in _GENERIC and not name.startswith("python") else ""
        entry = MicroEntry(micro_id, self.task_id, record.kind, operation, targets, (),
            (record.evidence_id,), record.evidence_id,
            (record.semantic_direction_id,) if record.semantic_direction_id else (),
            record.command_signature, condition_key, record.output_sha256, record.claim,
            record.counterexample_guidance, "unverified" if record.kind == "hypothesis" else "observed",
            record.kind != "hypothesis" and record.status not in {"timeout", "blocked"} and not record.output_truncated)
        self._source_entries[record.evidence_id] = micro_id
        return self._put(entry, " ".join((record.stdout, record.stderr, record.semantic_direction_label)))

    def add_lesson(self, hint, source_record, snapshot) -> MicroEntry | None:
        if source_record.task_id != self.task_id:
            raise ValueError("task conditional-experience scope violation")
        source = self._sources.get(source_record.evidence_id)
        if (source is None or source != source_record or source_record.kind == "hypothesis"
                or hint.source_channel != source_record.source_channel
                or type(hint.source_index) is not int or hint.source_index < 0
                or hint.source_index != getattr(source_record, "source_index", 0)
                or snapshot.snapshot_id != source_record.observed_snapshot_id
                or snapshot.fingerprint != source_record.fallback_snapshot):
            self._rejected_lessons += 1
            return None
        if (not hint.operation.strip() or not hint.lesson.strip()
                or any(item.predicate not in _FILE_PREDICATES | _SEMANTIC_PREDICATES for item in hint.premises)):
            self._rejected_lessons += 1
            return None
        condition_key = self._condition_key(source_record)
        premises = tuple(hint.premises)
        targets = tuple(dict.fromkeys(path for value in hint.target_paths if (path := _relative(value)) is not None))
        # Invalid target names must not disappear and accidentally broaden a rule.
        if len(targets) != len(set(hint.target_paths)):
            self._rejected_lessons += 1
            return None
        key = (self.task_id, "conditional_hypothesis", _normalized(hint.operation), targets,
               [(item.subject, item.predicate, item.value) for item in premises], condition_key,
               source_record.output_sha256, hint.lesson, hint.next_check)
        micro_id = "micro-" + _digest(key)[:24]
        source_entry = self._entries[self._source_entries[source_record.evidence_id]]
        entry = MicroEntry(micro_id, self.task_id, "conditional_hypothesis", hint.operation.strip(), targets,
            premises, (source_record.evidence_id,), source_record.evidence_id, source_entry.direction_ids,
            source_record.command_signature, condition_key, source_record.output_sha256,
            hint.lesson, hint.next_check, "unverified", source_entry.source_evidence_usable)
        return self._put(entry)

    def _match(self, entry, snapshot, validity_callback, reasons, file_cache, action=None) -> MicroMatch:
        record = self._sources[entry.representative_id]
        validity = validity_callback(record, snapshot)
        if validity not in {"valid", "changed", "unknown"}:
            validity = "unknown"
        if not entry.source_evidence_usable:
            validity = "unknown"
        declarations = tuple(getattr(action, "experience_premises", ())) if action is not None else ()
        started = time.perf_counter()
        self._condition_costs["premise_checks"] += len(entry.premises)
        states = tuple(_file_premise(item, snapshot, file_cache, self._condition_costs) if item.predicate in _FILE_PREDICATES
                       else _semantic_premise(item, declarations) for item in entry.premises)
        self._condition_costs["premise_check_seconds"] += time.perf_counter() - started
        condition = _condition(states, validity, entry.kind == "conditional_hypothesis")
        reasons = list(reasons)
        if not entry.source_evidence_usable:
            reasons.append("source_incomplete_or_unverified_not_promoted")
        if condition in {"changed", "declared_changed", "unknown"}:
            reasons.append("conditions_changed_or_unconfirmed_retry_allowed")
        if entry.kind == "conditional_hypothesis":
            reasons.append("model_conditional_hypothesis_not_causal_proof")
        return MicroMatch(entry, condition, validity, states, tuple(reasons))

    @staticmethod
    def _diverse(ranked, limit, reserve_conditional=False) -> tuple[MicroMatch, ...]:
        ranked.sort(key=lambda item: (-item[0], item[1].entry.micro_id))
        selected = []
        deferred = []
        seen = set()
        for _, match in ranked:
            group = (match.entry.kind, _normalized(match.entry.operation), tuple(sorted(match.entry.target_paths)))
            if group in seen:
                deferred.append(match)
            else:
                seen.add(group)
                selected.append(match)
        chosen = (selected + deferred)[:limit]
        if reserve_conditional and chosen and not any(item.entry.kind == "conditional_hypothesis" for item in chosen):
            conditional = next((item for _, item in ranked if item.entry.kind == "conditional_hypothesis"), None)
            if conditional is not None:
                # A category quota after the operation/scope eligibility gate,
                # not a utility score and not a change to execution priority.
                chosen[-1] = replace(conditional, match_reasons=(*conditional.match_reasons, "action_stage_conditional_category_slot"))
        return tuple(chosen)

    def retrieve(self, *, context, snapshot, limit: int, validity_callback: Callable) -> tuple[MicroMatch, ...]:
        if limit <= 0:
            return ()
        text = " ".join((context.task_goal, context.current_solution, *context.unresolved_issues,
                         *context.incomplete_plans, *context.analysis_and_conclusions,
                         *(item.claim for item in context.facts_and_evidence)))
        tokens = _tokens(text)
        focus_text = " ".join((*context.unresolved_issues, *context.incomplete_plans))
        focus_tokens = _tokens(focus_text)
        directions = {item.direction_id for item in context.semantic_directions}
        files = {path for value in re.findall(r"[\w./\\-]+\.[\w]+", text) if (path := _relative(value)) is not None}
        focus_files = {path for value in re.findall(r"[\w./\\-]+\.[\w]+", focus_text) if (path := _relative(value)) is not None}
        candidates = set(self._verifiers)
        for token in tokens:
            candidates.update(self._tokens.get(token, ()))
        for direction in directions:
            candidates.update(self._directions.get(direction, ()))
        for path in files:
            candidates.update(self._files.get(path, ()))
        ranked = []
        file_cache = {}
        for micro_id in candidates:
            entry = self._entries[micro_id]
            reasons = []
            overlap = len(tokens.intersection(self._entry_tokens[micro_id]))
            same_direction = bool(directions.intersection(entry.direction_ids))
            same_file = bool(files.intersection(entry.target_paths))
            focus_overlap = len(focus_tokens.intersection(self._entry_tokens[micro_id]))
            focus_file = bool(focus_files.intersection(entry.target_paths))
            if same_direction:
                reasons.append("same_semantic_direction")
            if same_file:
                reasons.append("explicit_context_file_overlap")
            if overlap:
                reasons.append(f"context_specific_token_overlap:{overlap}")
            if focus_file:
                reasons.append("current_issue_or_plan_file_overlap")
            if focus_overlap:
                reasons.append(f"current_issue_or_plan_token_overlap:{focus_overlap}")
            if entry.kind == "reusable_verifier":
                reasons.append("observed_public_verifier")
            match = self._match(entry, snapshot, validity_callback, reasons, file_cache)
            score = (12 * focus_file + 3 * min(focus_overlap, 4) + 4 * same_file
                     + 2 * same_direction + min(overlap, 4) + (match.source_validity == "valid"))
            ranked.append((score, match))
        return self._diverse(ranked, limit)

    @staticmethod
    def _command_signatures(action, snapshot) -> set[str]:
        root = Path(snapshot.location).resolve()
        signatures = set()
        for command in action.commands:
            cwd_path = Path(command.cwd)
            cwd_path = cwd_path if cwd_path.is_absolute() else root / cwd_path
            try:
                cwd = cwd_path.resolve().relative_to(root).as_posix()
            except (OSError, ValueError, RuntimeError):
                cwd = command.cwd
            argv = []
            for value in command.argv:
                if Path(value).is_absolute():
                    try:
                        value = "@workspace/" + Path(value).resolve().relative_to(root).as_posix()
                    except (OSError, ValueError, RuntimeError):
                        pass
                argv.append(value)
            signatures.add(_digest({"argv": tuple(argv), "cwd": cwd, "stdin": command.stdin}))
        return signatures

    def match_action(self, *, action, snapshot, limit: int, validity_callback: Callable) -> tuple[MicroMatch, ...]:
        if limit <= 0:
            return ()
        operation = _normalized(getattr(action, "experience_operation", ""))
        files = {path for value in getattr(action, "experience_targets", ()) if (path := _relative(value)) is not None}
        declarations = tuple(getattr(action, "experience_premises", ()))
        subjects = {item.subject for item in declarations}
        signatures = self._command_signatures(action, snapshot)
        candidates = set()
        for signature in signatures:
            candidates.update(self._commands.get(signature, ()))
        if operation:
            candidates.update(self._operations.get(operation, ()))
        for path in files:
            candidates.update(self._files.get(path, ()))
        ranked = []
        file_cache = {}
        for micro_id in candidates:
            entry = self._entries[micro_id]
            exact = entry.kind != "conditional_hypothesis" and entry.command_signature in signatures
            same_operation = bool(operation and operation == _normalized(entry.operation))
            same_file = bool(files.intersection(entry.target_paths))
            same_subject = bool(subjects.intersection(item.subject for item in entry.premises))
            specific_operation = same_operation and bool(_tokens(operation))
            if not exact and entry.target_paths and files and not same_file:
                continue
            if not exact and not ((specific_operation and (same_file or same_subject)) or (same_operation and same_file and same_subject)):
                continue
            reasons = []
            if exact:
                reasons.append("exact_command_and_cwd_signature")
            if same_operation:
                reasons.append("explicit_operation_match")
            if same_file:
                reasons.append("explicit_target_file_overlap")
            if same_subject:
                reasons.append("explicit_premise_subject_overlap")
            match = self._match(entry, snapshot, validity_callback, reasons, file_cache, action)
            score = 8 * exact + 4 * same_operation + 3 * same_file + 2 * same_subject
            ranked.append((score, match))
        return self._diverse(ranked, limit, reserve_conditional=True)

    def all(self) -> tuple[MicroEntry, ...]:
        return tuple(self._entries.values())

    def report(self) -> dict:
        return {"raw_source_count": len(self._sources), "micro_entry_count": len(self._entries),
                "aggregated_raw_entry_count": sum(item.kind != "conditional_hypothesis" for item in self._entries.values()),
                "conditional_hypothesis_count": sum(item.kind == "conditional_hypothesis" for item in self._entries.values()),
                "rejected_lessons": self._rejected_lessons,
                **self._condition_costs,
                "condition_check_cost_scope": "Cumulative local premise checks only; excludes source-validity callbacks and original CLI metrics. Local CPU and IO are not free.",
                "indexes": {"operation": len(self._operations), "file": len(self._files),
                            "token": len(self._tokens), "direction": len(self._directions), "command": len(self._commands)},
                "repetition_is_independent_confidence": False, "learned_utility": False,
                "causal_status": "not_established", "hard_blocking": False}
