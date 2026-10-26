"""Passive, method-independent reusable-evidence redundancy detector.

This is an operational measure, not an oracle for the usefulness of arbitrary
programs. Unsupported operations remain unknown, not nonredundant. No model or
agent memory, description, success declaration or direction label is consulted.
"""
from __future__ import annotations

from dataclasses import replace
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

REDUNDANCY_VERSION = "confirmed-reusable-call-v2"
LIMIT = 16 * 1024 * 1024
BINARY_LIMIT = 256 * 1024 * 1024
_BINARY_CACHE = {}


def hashed(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def local(root, cwd, value):
    try:
        working = Path(cwd)
        working = working if working.is_absolute() else root / working
        path = Path(value)
        path = Path(os.path.abspath(path if path.is_absolute() else working / path))
        relative = path.relative_to(root)
        cursor = root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
                return None
        return relative.as_posix(), path
    except (OSError, ValueError, RuntimeError):
        return None


def file_state(path, limit=LIMIT):
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        digest = hashlib.sha256()
        remaining = limit + 1
        with path.open("rb") as stream:
            while remaining:
                block = stream.read(min(1024 * 1024, remaining))
                if not block:
                    break
                digest.update(block)
                remaining -= len(block)
            if not remaining:
                return None
        return (digest.hexdigest(), path.stat().st_mode & 0o777)
    except OSError:
        return None


def binary_state(path):
    """Conda Linux Python exceeds 16 MiB. Hash it without repeated NAS reads.

    Cache only while file identity, size, permissions, mtime AND ctime agree.
    This does not cache task evidence or file-query dependencies across calls.
    """
    try:
        before = path.stat()
        key = (str(path), before.st_dev, before.st_ino, before.st_size,
               before.st_mode, before.st_mtime_ns, before.st_ctime_ns)
        if key in _BINARY_CACHE:
            return _BINARY_CACHE[key]
        result = file_state(path, BINARY_LIMIT)
        after = path.stat()
        after_key = (str(path), after.st_dev, after.st_ino, after.st_size,
                     after.st_mode, after.st_mtime_ns, after.st_ctime_ns)
        if key != after_key:
            return None
        if result is not None:
            if len(_BINARY_CACHE) >= 128:
                _BINARY_CACHE.clear()
            _BINARY_CACHE[key] = result
        return result
    except OSError:
        return None


def read_paths(name, args):
    """Direct explicit regular files only; no shell, recursive search or stdin."""
    args = list(args)
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
                    "-w", "-x", "-s", "--no-heading", "-H", "--with-filename", "--no-filename",
                    "-a", "--text", "-c", "--count", "-o", "--only-matching", "--no-config"}
        pattern = None
        while args:
            if args[0] == "--":
                args.pop(0)
                break
            if args[0] in switches:
                args.pop(0)
            elif args[0] in {"-A", "-B", "-C", "-m", "--max-count"}:
                if len(args) < 2 or not args[1].isdigit():
                    return None
                args = args[2:]
            elif args[0] == "-e" and len(args) >= 2 and pattern is None:
                pattern, args = args[1], args[2:]
            elif args[0].startswith("-"):
                return None
            else:
                break
        if pattern is None:
            if not args:
                return None
            args.pop(0)
    elif name != "cat":
        return None
    if args and args[0] == "--":
        args.pop(0)
    return args if args and all(x and not x.startswith("-") for x in args) else None


def is_check(name, args, phase):
    # Explicit pytest invocation or local Python probe, in EITHER arm and phase.
    # Putting an identical command in verification_commands must not change its
    # evidence eligibility. Actual side effects/errors are screened after execution.
    if name in {"pytest", "py.test"}:
        return True
    if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", name):
        return args[:2] == ["-m", "pytest"] or (len(args) == 1 and args[0].endswith(".py"))
    return False


def python_read(args):
    """Recognize only a tiny pure-read AST, without executing or eval-ing it."""
    if len(args) != 2 or args[0] != '-c':
        return None
    try:
        body = ast.parse(args[1]).body
    except (SyntaxError, ValueError):
        return None
    prefix = body[:-1]
    path_imported = any(isinstance(x, ast.ImportFrom) and x.module == 'pathlib' and x.level == 0
                        and len(x.names) == 1 and x.names[0].name == 'Path' and x.names[0].asname is None for x in prefix)
    if len(prefix) > 1 or (prefix and not path_imported):
        return None
    expr = body[-1].value if body and isinstance(body[-1], ast.Expr) else None
    if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == 'print'
            and len(expr.args) == 1 and not expr.keywords):
        return None
    read = expr.args[0]
    if not (isinstance(read, ast.Call) and not read.args and not read.keywords
            and isinstance(read.func, ast.Attribute)):
        return None
    opening = read.func.value
    if not (isinstance(opening, ast.Call) and isinstance(opening.func, ast.Name)
            and len(opening.args) == 1 and not opening.keywords
            and isinstance(opening.args[0], ast.Constant) and isinstance(opening.args[0].value, str)):
        return None
    if ((opening.func.id == 'Path' and path_imported and read.func.attr == 'read_text')
            or (opening.func.id == 'open' and not prefix and read.func.attr == 'read')):
        return [opening.args[0].value]
    return None


def capture(environment, directory, command, phase, workspace_hash):
    """Capture before AND after; hash credentials, never persist their values."""
    root = Path(directory).resolve()
    rewrite = environment._rewrite_workspace_references
    cmd = replace(command, argv=tuple(rewrite(x, root) for x in command.argv),
                  cwd=rewrite(command.cwd, root))
    if not cmd.argv or cmd.stdin is not None:
        return None
    cwd = local(root, ".", cmd.cwd)
    if not cwd or not cwd[1].is_dir():
        return None
    name = Path(cmd.argv[0]).name.casefold().removesuffix(".exe")
    args = list(cmd.argv[1:])
    paths = read_paths(name, args)
    pure_python = python_read(args) if re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", name) else None
    if pure_python:
        paths = pure_python
        # Do not mistake a project module named pathlib for the standard library.
        if any((base / item).exists() for base in (root, cwd[1]) for item in ('pathlib.py', 'pathlib')):
            return None
    kind = "read" if paths is not None else "check" if is_check(name, args, phase) else None
    if kind is None:
        return None
    executable = cmd.argv[0]
    if not Path(executable).is_absolute() and any(not x or not Path(x).is_absolute()
                                                  for x in os.environ.get("PATH", "").split(os.pathsep)):
        return None
    selected = shutil.which(executable)
    if not selected:
        return None
    binary = Path(selected).resolve()
    executor_state = binary_state(binary)
    if not executor_state or binary.is_relative_to(root):
        return None
    env = dict(os.environ)
    # These are rewritten by the common executor for each snapshot.
    env["RETRAC_WORKSPACE"] = "<workspace>"
    if env.get("BESTFGS_TASK_SOURCE_PATH") == "1":
        env["PYTHONPATH"] = "<workspace>/src:<workspace>/lib:<workspace>:" + env.get("PYTHONPATH", "")
    env_token = hashed(env)
    canonical = []
    for arg in args:
        info = local(root, cmd.cwd, arg) if Path(arg).is_absolute() else None
        canonical.append("<workspace>/" + info[0] if info else arg)
    operation = [name, canonical, cwd[0]]
    deps = []
    if kind == "read":
        for value in paths:
            info = local(root, cmd.cwd, value)
            state = file_state(info[1]) if info else None
            if not state:
                return None
            deps.append((info[0], state))
        # A narrowly proven equivalence: complete, single-file cat and sed.
        # The output must ALSO match; binary/no-newline differences don't count.
        if len(deps) == 1 and (pure_python or name == "cat" or (name == "sed" and args[:2] == ["-n", "1,$p"])):
            operation = ["full_file", deps[0][0], cwd[0]]
        condition = hashed([deps, env_token])
    else:
        if name not in {"pytest", "py.test"} and args[:2] != ["-m", "pytest"]:
            info = local(root, cmd.cwd, args[0])
            if not info or file_state(info[1]) is None:
                return None
        else:
            test_args = args[2:] if args[:2] == ["-m", "pytest"] else args
            switches = {"-q", "-v", "-vv", "-x", "--disable-warnings", "--no-header", "--no-summary"}
            for arg in test_args:
                if arg in switches:
                    continue
                info = local(root, cmd.cwd, arg.split("::", 1)[0])
                if arg.startswith('-') or not info or not info[1].exists():
                    return None
        # Tests may import any project file: never narrow to just the test file.
        condition = hashed([workspace_hash, env_token])
    return {"kind": kind, "operation_sha256": hashed(operation),
            "condition_sha256": condition, "executor_sha256": hashed([str(binary), executor_state]),
            "dependency_count": len(deps), "name": name,
            "runner": "pytest" if name in {'pytest', 'py.test'} or args[:2] == ['-m', 'pytest'] else None}


def evidence_output(text, evidence):
    """Ignore only pytest's summary duration; retain counts, failures and details."""
    if not evidence or evidence.get('runner') != 'pytest':
        return text
    return re.sub(r'(?m)^(?P<summary>=*\s*\d+ (?:passed|failed|skipped|error|errors|xfailed|xpassed)'
                  r'(?:, \d+ (?:passed|failed|skipped|error|errors|xfailed|xpassed|warnings?))*)'
                  r' in \d+(?:\.\d+)?s(?P<end>\s*=*\s*)$',
                  r'\g<summary> in <elapsed>s\g<end>', text)


class RedundancyDetector:
    def __init__(self):
        self.evidence = {}
        self.final_checks = set()

    def classify(self, before, after, result, phase, unchanged, observation, call_id):
        unknown = {"classification": "unknown", "reason": "unsupported_or_unobserved_dependencies",
                   "earlier_call_id": None}
        if before is None or after is None or before != after:
            return unknown
        if result.blocked or result.timed_out or result.output_truncated:
            return {**unknown, "reason": "incomplete_or_blocked_observation"}
        if not unchanged:
            return {**unknown, "reason": "workspace_side_effect"}
        kind = before["kind"]
        if kind == "read" and result.return_code not in ((0, 1) if before["name"] == "rg" else (0,)):
            return {**unknown, "reason": "read_error"}
        if kind == "check" and (result.return_code not in (0, 1) or any(
            marker in (result.stdout + "\n" + result.stderr).casefold()
            for marker in ("connection", "network", "timeout", "timed out", "modulenotfounderror",
                           "importerror", "permission denied", "no such file", "flaky", "random seed"))):
            return {**unknown, "reason": "check_retry_or_external_state_uncertain"}
        # For full-file equivalence, executable variants can share evidence only
        # after each variant has independently been fingerprinted and checked.
        key = (before["operation_sha256"], before["condition_sha256"], observation)
        prior = self.evidence.get(key)
        obligation = (before["operation_sha256"], before["condition_sha256"])
        final_due = kind == "check" and phase == "final_verification" and obligation not in self.final_checks
        if final_due:
            self.final_checks.add(obligation)
        # Same operation may not reuse evidence from a changed binary. Different
        # full-read tools are an explicitly supported equivalence, not a general rule.
        compatible = prior and (prior[1] == before["executor_sha256"] or prior[2] != before["name"])
        redundant = bool(compatible and not final_due)
        self.evidence[key] = (call_id, before["executor_sha256"], before["name"])
        return {"classification": "redundant" if redundant else "nonredundant",
                "reason": "reusable_evidence_no_new_obligation" if redundant else
                          "required_final_recheck" if final_due else "new_evidence_or_conditions",
                "earlier_call_id": prior[0] if compatible else None}


def aggregate_redundancy(metrics):
    """Aggregate the conservative, automatically confirmed lower bound.

    This deliberately does not claim to measure every kind of semantic waste.
    Unsupported calls remain ``unknown`` and are exposed through coverage and
    sensitivity bounds instead of being silently labelled useful or wasteful.
    """
    available = bool(metrics) and all(m.get("trace_complete") is True and
        m.get("redundancy_version") == REDUNDANCY_VERSION and
        all(type(m.get(k)) is int and m[k] >= 0 for k in
            ("tool_calls", "confirmed_reusable_calls", "unclassified_tool_calls")) and
        m["confirmed_reusable_calls"] + m["unclassified_tool_calls"] <= m["tool_calls"] for m in metrics)
    n = sum(m["tool_calls"] for m in metrics) if available else None
    r = sum(m["confirmed_reusable_calls"] for m in metrics) if available else None
    u = sum(m["unclassified_tool_calls"] for m in metrics) if available else None
    phases = None
    if available and all(isinstance(m.get('confirmed_reusable_by_phase'), dict) for m in metrics):
        phases = {}
        for phase in sorted({p for m in metrics for p in m['confirmed_reusable_by_phase']}):
            values = [m['confirmed_reusable_by_phase'].get(phase, {'tool_calls': 0, 'confirmed_reusable_calls': 0,
                      'unclassified_tool_calls': 0}) for m in metrics]
            if not all(all(type(v.get(k)) is int and v[k] >= 0 for k in
                           ('tool_calls', 'confirmed_reusable_calls', 'unclassified_tool_calls'))
                       and v['confirmed_reusable_calls'] + v['unclassified_tool_calls'] <= v['tool_calls'] for v in values):
                phases[phase] = None
                continue
            pn = sum(v['tool_calls'] for v in values)
            pr = sum(v['confirmed_reusable_calls'] for v in values)
            pu = sum(v['unclassified_tool_calls'] for v in values)
            phases[phase] = {'tool_calls': pn, 'confirmed_reusable_calls': pr, 'unclassified_tool_calls': pu,
                'rate': pr / pn if pn else None, 'classification_coverage': (pn - pu) / pn if pn else None}
    return {"redundancy_version": REDUNDANCY_VERSION, "confirmed_reusable_by_phase": phases,
            "confirmed_reusable_calls": r, "unclassified_tool_calls": u,
            "confirmed_reusable_call_rate": r / n if n else None,
            "confirmed_reusable_status": "automatic_operational_lower_bound" if available else "unavailable",
            "classification_coverage": (n - u) / n if n else None,
            "unknown_call_rate": u / n if n else None,
            "confirmed_reusable_rate_sensitivity_bounds": [r / n, (r + u) / n] if n else None,
            "bounds_note": "Treating every unknown as either non-reusable or reusable gives a sensitivity range, not a confidence interval and not a bound on all semantic waste."}


def aggregate_mechanical(metrics):
    available = bool(metrics) and all(m.get('trace_complete') is True and
        type(m.get('mechanical_repeat_calls')) is int and type(m.get('tool_calls')) is int
        and 0 <= m['mechanical_repeat_calls'] <= m['tool_calls'] for m in metrics)
    n = sum(m['tool_calls'] for m in metrics) if available else None
    r = sum(m['mechanical_repeat_calls'] for m in metrics) if available else None
    phases = None
    if available and all(isinstance(m.get('mechanical_repeat_by_phase'), dict) for m in metrics):
        phases = {}
        for phase in sorted({p for m in metrics for p in m['mechanical_repeat_by_phase']}):
            values = [m['mechanical_repeat_by_phase'].get(phase, {'tool_calls': 0, 'mechanical_repeat_calls': 0}) for m in metrics]
            if not all(type(v.get('tool_calls')) is int and type(v.get('mechanical_repeat_calls')) is int for v in values):
                phases[phase] = {'tool_calls': None, 'mechanical_repeat_calls': None, 'mechanical_repeat_rate': None}
                continue
            calls = sum(v['tool_calls'] for v in values)
            repeats = sum(v['mechanical_repeat_calls'] for v in values)
            phases[phase] = {'tool_calls': calls, 'mechanical_repeat_calls': repeats,
                             'mechanical_repeat_rate': repeats / calls if calls else None}
    return {'mechanical_repeat_calls': r, 'mechanical_repeat_rate': r / n if n else None,
            'mechanical_repeat_by_phase': phases}
