"""Method-independent, append-only CLI accounting. Never used to choose actions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections import Counter
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from .redundancy import REDUNDANCY_VERSION, RedundancyDetector, capture, aggregate_redundancy, evidence_output

METRIC_VERSION = "cli-comparison-v2"
METRIC_REPORT_VERSION = "cli-metrics-report-v3"
METRIC_INTERPRETATION = {
    "mechanical_repeat": "Same normalized command, observable workspace and output; both occurrences leave workspace unchanged.",
    "semantic_redundancy": "Automatically detected reusable evidence with unchanged relevant conditions and no new verification obligation; unknowns remain explicit.",
    "phase_policy": "All actual calls in denominator. One final check per operation/condition is allowed; repeated checks are not blanket-exempt.",
    "legacy_aliases": "v1 traces retain historical mechanical aliases. v2 redundant_tool_calls is the NEW metric; never pool versions.",
    "cost_scope": "CLI calls exclude automatic syntax gates and internal memory/file checks; report separate runtime costs.",
}
IGNORED = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def workspace_digest(root):
    """Observable file contents + modes; intentionally excludes VCS and test caches.

    Symlinks are hashed as links, never traversed outside the task workspace.
    This is NOT a fingerprint of external processes, network or the whole OS.
    """
    rows = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED)
        for name in sorted(files + [d for d in dirs if (Path(directory) / d).is_symlink()]):
            if name.startswith(".coverage"):
                continue
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                rows.append((relative, "link", os.readlink(path)))
            elif path.is_file():
                with path.open("rb") as stream:
                    content = hashlib.file_digest(stream, "sha256").hexdigest()
                rows.append((relative, path.stat().st_mode & 0o777, content))
    return digest(sorted(rows))


class ExperimentRecorder:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Each run must have a fresh trace; never combine attempts silently.
        with self.path.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": "header", "metric_version": METRIC_VERSION,
                                     "redundancy_version": REDUNDANCY_VERSION}) + "\n")
        self.stack = []
        self.next_round = 0
        self.next_call = 0
        self.seen = set()
        self.detector = RedundancyDetector()

    def emit(self, event, **fields):
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"event": event, **fields}, ensure_ascii=True) + "\n")

    @contextmanager
    def batch(self, phase):
        # Verification nested inside an action belongs to that same feedback batch.
        root = self.stack[0][1] if self.stack else {"id": None}
        phase = "functional_verification" if phase == "verification" and self.stack else phase
        phase = "final_verification" if phase == "verification" else phase
        self.stack.append((phase, root))
        try:
            yield
        finally:
            self.stack.pop()

    def command(self, environment, directory, command, invoke):
        started = time.monotonic()
        before = workspace_digest(directory)
        aliases = sorted({str(directory.resolve()), directory.resolve().as_posix(),
                          str(environment.seed_workspace), environment.seed_workspace.as_posix()}, key=len, reverse=True)

        def normalize(text):
            for alias in aliases:
                text = re.sub(re.escape(alias) + r"(?=$|[\\/\"'\s\),;:\]])", "<workspace>", text)
            return text

        signature = digest({"argv": [normalize(p) for p in command.argv],
                            "cwd": normalize(command.cwd), "stdin": normalize(command.stdin) if command.stdin is not None else None,
                            "timeout": command.timeout_seconds or environment.config.command_timeout_seconds})
        phase, root = self.stack[-1] if self.stack else ("standalone", {"id": None})
        try:
            evidence_before = capture(environment, directory, command, phase, before)
        except (OSError, ValueError, RuntimeError):
            evidence_before = None
        if root["id"] is None:
            self.next_round += 1
            root["id"] = self.next_round
            self.emit("round_start", round_id=root["id"], phase=self.stack[0][0] if self.stack else phase)
        self.next_call += 1
        call_id = self.next_call
        self.emit("tool_start", call_id=call_id, round_id=root["id"], phase=phase,
                  command_sha256=signature, before_sha256=before)
        measure_seconds = time.monotonic() - started
        result = invoke()
        started = time.monotonic()
        after = workspace_digest(directory)
        observation = digest([result.return_code, normalize(result.stdout), normalize(result.stderr),
                              result.blocked, result.timed_out])
        key = (signature, before, observation)
        unchanged = before == after
        repeat = unchanged and key in self.seen
        if unchanged:
            self.seen.add(key)
        try:
            evidence_after = capture(environment, directory, command, phase, after)
        except (OSError, ValueError, RuntimeError):
            evidence_after = None
        evidence_observation = digest([result.return_code,
            evidence_output(normalize(result.stdout), evidence_before),
            evidence_output(normalize(result.stderr), evidence_before), result.blocked, result.timed_out])
        classification = self.detector.classify(evidence_before, evidence_after, result, phase,
                                               unchanged, evidence_observation, call_id)
        self.emit("tool_end", call_id=call_id, after_sha256=after, observation_sha256=observation,
                  redundant=classification['classification'] == 'redundant', mechanical_repeat=repeat,
                  redundancy=classification, dependency_evidence=evidence_before,
                  evidence_observation_sha256=evidence_observation,
                  output_truncated=result.output_truncated,
                  workspace_unchanged=unchanged, return_code=result.return_code,
                  blocked=result.blocked, timed_out=result.timed_out, duration_seconds=result.duration_seconds,
                  instrumentation_seconds=measure_seconds + time.monotonic() - started)
        return result

    def summary(self):
        return summarize_trace(self.path)


def summarize_trace(path):
    raw = Path(path).read_bytes()
    events = []
    complete = True
    for line in raw.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            complete = False
    if not events or events[0].get("metric_version") not in {METRIC_VERSION, "cli-comparison-v1"}:
        raise ValueError("Unknown CLI metric trace version")
    version = events[0]['metric_version']
    modern = version == METRIC_VERSION
    starts = [e for e in events if e["event"] == "tool_start"]
    ends = {e["call_id"]: e for e in events if e["event"] == "tool_end"}
    rounds = [e for e in events if e["event"] == "round_start"]
    redundant = sum(bool(e["redundant"]) for e in ends.values())
    start_ids = [e['call_id'] for e in starts]
    end_events = [e for e in events if e['event'] == 'tool_end']
    complete = (complete and len(starts) == len(ends) == len(end_events)
                and len(set(start_ids)) == len(start_ids) and set(start_ids) == set(ends))
    if modern:
        complete = complete and events[0].get('redundancy_version') == REDUNDANCY_VERSION and all(
            e.get('redundancy', {}).get('classification') in {'redundant', 'nonredundant', 'unknown'}
            and e.get('redundant') == (e.get('redundancy', {}).get('classification') == 'redundant')
            and type(e.get('mechanical_repeat')) is bool for e in ends.values())
    by_phase = {}
    for phase in sorted({e['phase'] for e in starts}):
        selected = [e for e in starts if e['phase'] == phase]
        repeats = sum(bool(ends.get(e['call_id'], {}).get('redundant')) for e in selected)
        by_phase[phase] = {'tool_calls': len(selected), 'redundant_tool_calls': repeats,
                           'redundancy_unknown_calls': sum(ends.get(e['call_id'], {}).get('redundancy', {}).get('classification') == 'unknown' for e in selected) if modern else None,
                           'rate': repeats / len(selected) if all(e['call_id'] in ends for e in selected) else None}
    result = {"metric_version": version, "interaction_rounds": len(rounds),
            "rounds_by_phase": dict(Counter(e["phase"] for e in rounds)),
            "tool_calls": len(starts), "completed_tool_calls": len(ends),
            "tool_calls_by_phase": dict(Counter(e["phase"] for e in starts)),
            "redundancy_by_phase": by_phase,
            "redundant_tool_calls": redundant,
            "tool_call_redundancy_rate": redundant / len(starts) if starts and complete else None,
            "blocked_tool_calls": sum(e["blocked"] for e in ends.values()),
            "timed_out_tool_calls": sum(e["timed_out"] for e in ends.values()),
            "instrumentation_seconds": sum(e["instrumentation_seconds"] for e in ends.values()),
            "trace_complete": complete, "trace_sha256": hashlib.sha256(raw).hexdigest()}
    mechanical_phases = {phase: {'tool_calls': counts['tool_calls'],
        'redundant_tool_calls': sum(bool(ends.get(e['call_id'], {}).get('mechanical_repeat' if modern else 'redundant'))
                                  for e in starts if e['phase'] == phase)} for phase, counts in by_phase.items()}
    mechanical = sum(bool(e.get('mechanical_repeat' if modern else 'redundant')) for e in ends.values())
    result.update(mechanical_repeat_report({**result, 'redundant_tool_calls': mechanical,
                                           'redundancy_by_phase': mechanical_phases}))
    if modern:
        result['redundancy_version'] = REDUNDANCY_VERSION
        result['redundancy_unknown_calls'] = sum(e['redundancy']['classification'] == 'unknown' for e in ends.values()
                                                if isinstance(e.get('redundancy'), dict))
        result['redundancy_reason_counts'] = dict(Counter(e.get('redundancy', {}).get('reason', 'missing') for e in ends.values()))
        # Keep observed counts even for interrupted traces; full-trace rates are null.
        report = aggregate_redundancy([result])
        result.update({k: v for k, v in report.items() if k not in {'redundant_tool_calls', 'redundancy_unknown_calls'}})
    return result


def mechanical_repeat_report(metrics):
    """New presentation over v1 measurements; no relabeling of repeat as waste."""
    complete = metrics.get("trace_complete") is True
    calls, repeats = metrics.get("tool_calls"), metrics.get("redundant_tool_calls")
    valid = (complete and type(calls) is int and type(repeats) is int
             and 0 <= repeats <= calls)
    phases = metrics.get("redundancy_by_phase")
    by_phase = None
    if isinstance(phases, dict):
        by_phase = {}
        for phase, counts in phases.items():
            if not isinstance(counts, dict):
                by_phase[phase] = {"tool_calls": None, "mechanical_repeat_calls": None,
                                   "mechanical_repeat_rate": None}
                continue
            n, r = counts.get("tool_calls"), counts.get("redundant_tool_calls")
            known = valid and type(n) is int and type(r) is int and 0 <= r <= n
            by_phase[phase] = {"tool_calls": n if known else None,
                               "mechanical_repeat_calls": r if known else None,
                               "mechanical_repeat_rate": r / n if known and n else None}
    return {"metric_report_version": METRIC_REPORT_VERSION,
            "mechanical_repeat_calls": repeats if valid else None,
            "mechanical_repeat_rate": repeats / calls if valid and calls else None,
            "mechanical_repeat_by_phase": by_phase,
            "avoidable_repeat_rate": None, "avoidable_repeat_status": "requires_contextual_audit",
            "metric_interpretation": dict(METRIC_INTERPRETATION)}


def measured_batch(phase):
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            if self.recorder is None:
                return function(self, *args, **kwargs)
            with self.recorder.batch(phase):
                return function(self, *args, **kwargs)
        return wrapped
    return decorate


def measured_command(function):
    @wraps(function)
    def wrapped(self, directory, command):
        if self.recorder is None:
            return function(self, directory, command)
        return self.recorder.command(self, directory, command, lambda: function(self, directory, command))
    return wrapped
