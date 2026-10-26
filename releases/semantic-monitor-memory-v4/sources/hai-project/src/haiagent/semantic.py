"""Deterministic, bounded action profiles for task-local exploration control.

This is deliberately not an LLM judge.  It removes incidental shell spelling
such as numbered temporary files, classifies the operation, and records concrete
workspace targets.  A direction profile is evidence for a reminder, never proof
that two arbitrary programs are equivalent or that an approach cannot work.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex


_TMP = re.compile(r"(?<![\w.-])(?:/tmp|/var/tmp)/[A-Za-z0-9_.-]+")
_HEREDOC = re.compile(r"(?m)(<<-?\s*['\"]?)[A-Za-z_][A-Za-z0-9_]*(['\"]?)")
_SPACE = re.compile(r"\s+")
_PATH = re.compile(r"(?<![\w.-])(?:/app/[^\s'\";|&<>]+|(?:\.?\.?/)?[\w.-]+(?:/[\w.-]+)+|[\w.-]+\.(?:py|sh|json|ya?ml|toml|csv|tsv|md|txt|nc|tif|pdb|m))")
_SHELLS = {'bash', 'sh', 'zsh', 'dash', 'ksh'}
_BOUNDARIES = {'|', '||', '&&', ';'}
_SHELL_WORDS = {'do', 'done', 'then', 'fi', 'if', 'for', 'while', 'case', 'esac',
                'in', 'time', 'command', 'builtin', 'exec', 'env', 'sudo'}
_SCOPE = re.compile(
    r"(?ix)(?:"
    r"\b\d+\s*[,\-:]\s*\d+p?\b|"
    r"\bNR\s*(?:==|>=|<=|>|<)\s*\d+(?:\s*(?:&&|,)\s*NR\s*(?:==|>=|<=|>|<)\s*\d+)?|"
    r"--(?:offset|start|end|limit|page|skip|count|lines?|after-context|before-context|max-count)"
    r"(?:=|\s+)\S+|"
    r"-(?:A|B|C)\s*\d+|"
    r"\+\d+"
    r")")


def _canonical(text: str) -> str:
    value = _TMP.sub('/tmp/__HAI_TMP__', text)
    value = _HEREDOC.sub(r'\1__HAI_HEREDOC__\2', value)
    return _SPACE.sub(' ', value).strip()[:12000]


def _target(value: str, cwd: str) -> str | None:
    value = value.rstrip('.,:)').replace('\\', '/')
    if value.startswith(('/tmp/', '/var/tmp/')):
        return None
    if value.startswith('/app/'):
        value = value[5:]
    elif value == '/app':
        return '.'
    elif value.startswith('/'):
        return None
    base = PurePosixPath(cwd.replace('\\', '/'))
    if str(base).startswith('/app'):
        try:
            base = base.relative_to('/app')
        except ValueError:
            base = PurePosixPath('.')
    path = PurePosixPath(base, value)
    parts = []
    for part in path.parts:
        if part in ('', '.'):
            continue
        if part == '..':
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    result = '/'.join(parts) or '.'
    return result[:300]


def _kind(command: str) -> str:
    lower = command.casefold()
    if any(token in lower for token in ('pytest', 'unittest', 'npm test', 'cargo test', 'ctest')):
        return 'verify'
    if re.search(r"(?:^|[;&|]\s*)(?:cat\s+[^|>]+>|sed\s+-i|tee\s+|cp\s+|mv\s+|touch\s+|mkdir\s+|apply_patch)", lower):
        return 'modify'
    if any(token in lower for token in ('grep ', 'rg ', 'find ', 'fd ')):
        return 'search'
    if any(token in lower for token in ('cat ', 'sed -n', 'head ', 'tail ', 'ls ', 'tree ', 'stat ')):
        return 'inspect'
    if any(token in lower for token in ('pip install', 'apt-get', 'apt ', 'npm install', 'conda install')):
        return 'environment'
    return 'execute'


def _shell_payload(argv: list[str]) -> str:
    """Unwrap the script passed to a conventional shell, when present."""
    if not argv:
        return ''
    program = Path(str(argv[0])).name.casefold()
    if program not in _SHELLS:
        return shlex.join(str(value) for value in argv)
    for index, value in enumerate(argv[1:], 1):
        if isinstance(value, str) and value.startswith('-') and 'c' in value[1:]:
            return str(argv[index + 1]) if index + 1 < len(argv) else ''
    return shlex.join(str(value) for value in argv[1:])


def _tokens(command: str) -> list[str]:
    try:
        # punctuation_chars makes pipelines visible instead of gluing them to
        # adjacent text.  Fall back conservatively for malformed shell snippets.
        lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|')
        lexer.whitespace_split = True
        lexer.commenters = ''
        return list(lexer)[:256]
    except (ValueError, TypeError):
        return re.findall(r"&&|\|\||[;|]|[^\s;|&]+", command)[:256]


def _shape(command: str) -> tuple[list[str], list[str], list[str]]:
    """Return executable chain and bounded stable lexical anchors.

    This is deliberately syntactic rather than an open-ended semantic judge.
    It prevents all ``bash -lc`` actions collapsing together while treating
    numbered temporary wrapper scripts as the same attempted direction.
    """
    tokens = _tokens(command)
    chain, anchors = [], []
    expect_program = True
    for raw in tokens:
        token = raw.strip()
        if not token:
            continue
        if token in _BOUNDARIES:
            expect_program = True
            continue
        lower = token.casefold()
        if expect_program:
            if ('=' in token and not token.startswith(('=', '/', './', '../'))
                    and token.split('=', 1)[0].replace('_', '').isalnum()):
                continue
            if lower in _SHELL_WORDS:
                continue
            if token.startswith(('<', '>')):
                continue
            chain.append(Path(token).name.casefold()[:80])
            expect_program = False
            continue
        if token == '/tmp/__HAI_TMP__' or token.startswith(('/tmp/', '/var/tmp/')):
            continue
        if token.startswith('-'):
            anchors.append(token.casefold()[:80])
            continue
        # Numeric arguments may be exploration coordinates (line/page/offset),
        # so they are intentionally retained.  Only temporary path identities
        # are normalized above; silently dropping numbers merges distinct reads.
        if _PATH.fullmatch(token):
            continue
        if lower not in _SHELL_WORDS:
            anchors.append(lower[:80])
    scopes = [_SPACE.sub('', match.group(0)).casefold()[:120]
              for match in _SCOPE.finditer(command)]
    return (list(dict.fromkeys(chain))[:8], list(dict.fromkeys(anchors))[:12],
            list(dict.fromkeys(scopes))[:12])


def action_profile(decision: dict, workspace: Path) -> dict:
    """Return a stable coarse direction plus a stricter normalized action key."""
    argv = [str(value) for value in (decision.get('argv') or [])]
    # Keep argument boundaries.  Joining with spaces makes ["a b"] collide with
    # ["a", "b"], which can turn distinct actions into a false intervention.
    canonical_argv = [_canonical(value) for value in argv]
    canonical = json.dumps(canonical_argv, ensure_ascii=False,
                           separators=(',', ':'))
    payload = _canonical(_shell_payload(argv))
    cwd = str(decision.get('cwd') or '.')
    targets = []
    for match in _PATH.findall(canonical):
        value = _target(match, cwd)
        if value and value not in targets:
            targets.append(value)
    targets = targets[:12]
    outer_program = Path(argv[0]).name.casefold() if argv else 'unknown'
    tool_chain, anchors, exploration_scope = _shape(payload)
    program = tool_chain[0] if tool_chain else outer_program
    kind = _kind(payload)
    # Direction is intentionally coarser than exact action identity.  Stalling
    # still requires repeated evidence or a long no-change streak, limiting
    # false positives when several useful reads share one target.
    payload_sha256 = hashlib.sha256(payload.encode()).hexdigest()
    stdin = decision.get('stdin')
    stdin_direction_sha256 = (hashlib.sha256(_canonical(stdin).encode()).hexdigest()
                              if isinstance(stdin, str) else None)
    direction_basis = [kind, tool_chain or [program], targets, anchors,
                       exploration_scope, payload_sha256, stdin_direction_sha256]
    direction_key = hashlib.sha256(json.dumps(direction_basis, sort_keys=True).encode()).hexdigest()
    action_key = hashlib.sha256(json.dumps(
        [canonical_argv, cwd, stdin], ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest()
    summary_targets = ', '.join(targets[:4]) if targets else 'workspace/environment'
    return {'direction_key': direction_key, 'action_key': action_key, 'kind': kind,
            'program': program, 'tool_chain': tool_chain or [program],
            'anchors': anchors, 'exploration_scope': exploration_scope,
            'payload_sha256': payload_sha256,
            'stdin_direction_sha256': stdin_direction_sha256,
            'targets': targets,
            'summary': (f"{kind} via {' -> '.join(tool_chain or [program])}: {summary_targets}; "
                        f"scope={','.join(exploration_scope[:3]) or 'unspecified'}")[:500],
            'canonical_sha256': hashlib.sha256(canonical.encode()).hexdigest()}


def requested_paths(instruction: str) -> list[str]:
    """Extract only explicit task workspace paths; existence is not success."""
    found = []
    for match in _PATH.findall(instruction):
        value = _target(match, '.')
        if value and value != '.' and value not in found:
            found.append(value)
    return found[:24]


def delivery_progress(workspace: Path, instruction: str) -> dict:
    rows = []
    for relative in requested_paths(instruction):
        path = workspace / relative
        try:
            exists = path.exists() and path.is_relative_to(workspace)
            size = path.stat().st_size if exists and path.is_file() else None
        except (OSError, ValueError):
            exists, size = False, None
        rows.append({'path': relative, 'exists': exists, 'bytes': size})
    return {'semantics': ('Public requested-path existence only; it is not correctness, completeness, '
                          'or official success.'), 'requested_paths': rows,
            'existing': sum(row['exists'] for row in rows), 'total': len(rows)}
