"""Deterministic, bounded model views; never mutate observations or task memory."""
from __future__ import annotations

import hashlib
import json
import re
import shlex

from .semantic import project_context_for_prompt

VERSION = 'terminal-views-v2'
DIAGNOSTIC = re.compile(r'error|fail|exception|traceback|assert|conflict|denied|not found|no such|warning|^E\s|\bpassed\b|\bskipped\b|^FAILED|^ERROR', re.I)
SHELL_OPS = set('|&;<>()')

def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def clip(text, limit):
    if len(text) <= limit:
        return text
    marker = '\n[... omitted ...]\n'
    if limit <= len(marker):
        return '[omitted]'[:limit]
    available = limit - len(marker)
    head = available // 2
    return text[:head] + marker + text[-(available-head):]

def classify(argv):
    args = list(argv)
    if not args:
        return 'generic'
    exe = args[0].replace('\\', '/').rsplit('/', 1)[-1]
    if exe in ('bash', 'sh', 'zsh'):
        if len(args) != 3 or args[1] not in ('-c', '-lc') or any(c in args[2] for c in ('$', '`', '\n')):
            return 'generic'
        try:
            tokens = list(shlex.shlex(args[2], posix=True, punctuation_chars='|&;<>()'))
            if any(t and set(t) <= SHELL_OPS for t in tokens):
                return 'generic'
            args = shlex.split(args[2])
        except ValueError:
            return 'generic'
        # Only one simple command is unwrapped. No nested shell/wrapper interpretation.
        if not args or args[0].rsplit('/', 1)[-1] in ('bash', 'sh', 'zsh'):
            return 'generic'
        exe = args[0].replace('\\', '/').rsplit('/', 1)[-1]
    if exe in ('pytest', 'py.test') or (re.fullmatch(r'python[\d.]*', exe) and args[1:3] in (['-m', 'pytest'], ['-m', 'unittest'])):
        return 'test'
    if exe in ('npm', 'cargo', 'go') and args[1:2] == ['test']:
        return 'test'
    if exe in ('ls', 'find', 'tree'):
        return 'listing'
    if exe in ('rg', 'grep'):
        return 'search'
    if exe in ('cat', 'sed', 'head', 'tail'):
        return 'read'
    if exe == 'git' and args[1:2] == ['diff']:
        return 'diff'
    if exe == 'git' and args[1:2] == ['status']:
        return 'listing'
    if exe in ('make', 'cmake', 'ninja', 'gcc', 'g++', 'cargo'):
        return 'build'
    if exe in ('pip', 'pip3', 'npm', 'uv') or (re.fullmatch(r'python[\d.]*', exe) and args[1:3] == ['-m', 'pip']):
        return 'install'
    return 'generic'

def diagnostic_category(argv):
    """Conservative diagnostic hint, separate from output compression.

    Recognize static cd/AND chains and read pipelines, not arbitrary shell
    programs. This is not an execution authorization or a redundancy verdict.
    Runtime additionally requires success and an unchanged workspace.
    """
    def simple(args):
        if not args:
            return 'generic'
        exe = args[0].replace('\\', '/').rsplit('/', 1)[-1]
        if exe in {'bash', 'sh', 'zsh'}:
            return 'generic'
        if exe == 'find' and any(a in {'-delete', '-exec', '-execdir', '-ok', '-okdir',
                                      '-fprint', '-fprint0', '-fprintf', '-fls'} for a in args[1:]):
            return 'generic'
        if exe in {'rg', 'grep'} and any(a == '--pre' or a.startswith('--pre=') for a in args[1:]):
            return 'generic'
        if exe == 'git' and any(a == '--output' or a.startswith('--output=') for a in args[1:]):
            return 'generic'
        if exe == 'sed' and not (len(args) >= 3 and args[1] == '-n'
                                and re.fullmatch(r'\d+(?:,\d+)?p', args[2])):
            return 'generic'
        if exe in {'wc', 'uniq'}:
            return 'read'
        category = classify(args)
        return category if category in {'read', 'listing', 'search', 'diff'} else 'generic'

    args = list(argv)
    if not args:
        return 'generic'
    exe = args[0].replace('\\', '/').rsplit('/', 1)[-1]
    if exe not in {'bash', 'sh', 'zsh'}:
        return simple(args)
    if len(args) != 3 or args[1] not in {'-c', '-lc'}:
        return 'generic'
    script = args[2]
    if any(c in script for c in ('$', '`', '\n', '\r', '#', '\\')):
        return 'generic'
    try:
        lexer = shlex.shlex(script, posix=True, punctuation_chars='|&;<>()')
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return 'generic'
    segments, operators, part = [], [], []
    for token in tokens:
        if token and set(token) <= SHELL_OPS:
            if token not in {'&&', '|'} or not part:
                return 'generic'
            segments.append(part)
            operators.append(token)
            part = []
        else:
            part.append(token)
    if not part:
        return 'generic'
    segments.append(part)
    categories = []
    for i, segment in enumerate(segments):
        if segment[0] == 'cd':
            if (len(segment) != 2 or segment[1].startswith(('-', '~')) or
                    i >= len(operators) or operators[i] != '&&' or
                    (i > 0 and operators[i-1] != '&&')):
                return 'generic'
            continue
        category = simple(segment)
        if category == 'generic':
            return 'generic'
        categories.append(category)
    return categories[-1] if categories else 'generic'


def compress_stream(text, category, limit):
    """Excerpts, not semantic summaries; L numbers refer to captured output lines."""
    if len(text) <= limit:
        return text
    # Bound selection work. Oversize output gets a conservative head/tail view.
    if len(text) > 250_000 or category in ('generic', 'read'):
        return clip(text, limit)
    lines = text.splitlines(keepends=True)
    selected = set()
    used = 80
    def add(index):
        nonlocal used
        if index in selected or not 0 <= index < len(lines):
            return
        cost = len(lines[index]) + 30
        if used + cost <= limit:
            selected.add(index)
            used += cost
    if category in ('test', 'build', 'install'):
        # Both failure diagnostics and footer are represented, not just success tail.
        hits = [i for i, line in enumerate(lines) if DIAGNOSTIC.search(line)]
        for i in hits[:4] + hits[-4:]:
            add(i)
        for i in range(max(0, len(lines)-6), len(lines)):
            add(i)
        for i in hits:
            for j in (i-1, i, i+1):
                add(j)
    elif category == 'diff':
        # Keep path/hunk identifiers first; never pretend this is an applicable patch.
        for i, line in enumerate(lines):
            if line.startswith(('diff --git ', '--- ', '+++ ', '@@')):
                add(i)
    for i in list(range(min(4, len(lines)))) + list(range(max(0, len(lines)-4), len(lines))):
        add(i)
    for i in range(len(lines)):
        add(i)
    if not selected:
        return clip(text, limit)
    result = '[excerpt only; omitted captured lines are not evidence of absence]\n'
    previous = -1
    for i in sorted(selected):
        if i > previous + 1:
            result += '[...]\n'
        result += f'[L{i+1}] ' + lines[i].rstrip('\r\n') + '\n'
        previous = i
    if previous < len(lines)-1:
        result += '[...]\n'
    return clip(result, limit)

def fit_json_text(text, allowance):
    """Limit escaped JSON characters, not just the unescaped string."""
    if len(compact(text)) - 2 <= allowance:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if len(compact(clip(text, mid))) - 2 <= allowance:
            lo = mid
        else:
            hi = mid - 1
    return clip(text, lo)

def observation_sources(outcome, max_chars):
    channels = (('command', outcome.command_results), ('automatic_validation', outcome.validation_results),
                ('functional_validation', outcome.functional_validation_results))
    sources, originals = [], []
    counts = {name: len(results) for name, results in channels}
    for channel, results in channels:
        for index, result in enumerate(results):
            category = classify(result.command.argv)
            sources.append({'source_channel': channel, 'source_index': index,
                'argv': clip(compact(result.command.argv), 240), 'cwd': clip(result.command.cwd, 160),
                'return_code': result.return_code, 'timed_out': result.timed_out, 'blocked': result.blocked,
                'output_truncated': result.output_truncated, 'display_truncated': True,
                'compression': VERSION + '/' + category,
                'stdout_chars': len(result.stdout), 'stderr_chars': len(result.stderr),
                'captured_stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest(),
                'captured_stderr_sha256': hashlib.sha256(result.stderr.encode()).hexdigest(),
                'stdout': '', 'stderr': ''})
            originals.append((result, category))
    remaining = max_chars - len(compact(sources)) - len(sources)
    if remaining < 0:
        raise ValueError('Observation budget cannot fit source identities; increase max_observation_chars')
    streams = [(i, stream, getattr(result, stream), category,
                3 if stream == 'stderr' or result.return_code != 0 or result.timed_out or result.blocked else 1)
               for i, (result, category) in enumerate(originals) for stream in ('stdout', 'stderr')]
    costs = [len(compact(raw)) - 2 for _, _, raw, _, _ in streams]
    allocations = allocate_stream_budgets(costs, [weight for _, _, _, _, weight in streams], remaining)
    for (index, stream, raw, category, _), allowance in zip(streams, allocations):
        sources[index][stream] = fit_json_text(compress_stream(raw, category, allowance), allowance)
    for source, (result, category) in zip(sources, originals):
        source['display_truncated'] = source['stdout'] != result.stdout or source['stderr'] != result.stderr
    assert len(compact(sources)) <= max_chars
    return sources, counts

def allocate_stream_budgets(costs, weights, budget):
    """Weighted water-filling: empty/short streams leave capacity for others."""
    allocated = [0] * len(costs)
    while budget > 0:
        active = [i for i, cost in enumerate(costs) if allocated[i] < cost]
        if not active:
            break
        total_weight = sum(weights[i] for i in active)
        pool = budget
        for i in sorted(active, key=lambda n: (-weights[n], n)):
            amount = min(costs[i] - allocated[i], max(1, pool * weights[i] // total_weight), budget)
            allocated[i] += amount
            budget -= amount
    return allocated

def memory_panel(context, rules, *, mode, max_chars=2500, retrieved_count=None):
    """Reserve space for existing selected rules, not a second memory store."""
    payload = {'policy': VERSION, 'mode': mode, 'rules': [], 'observed_facts': [],
               'omitted_rules': max(0, (retrieved_count or 0) - len(rules)), 'omitted_facts': 0,
               'caution': 'Task-local untrusted evidence. Check conditions and current state; past verification is not current validity. Missing records do not prove no counterexample.'}
    if mode == 'off':
        payload['caution'] = 'Extra memory disabled. Use ordinary task context.'
        return compact(payload)
    for rule in rules:
        candidate = [*payload['rules'], rule]
        if len(compact(dict(payload, rules=candidate))) + 40 <= max_chars:
            payload['rules'] = candidate
        else:
            payload['omitted_rules'] += 1
    # Prefer verified, recent facts. Preserve attribution as a whole record.
    ranked = sorted(enumerate(context.facts_and_evidence),
                    key=lambda p: (p[1].verified == 'yes', p[0]), reverse=True)
    for _, fact in ranked:
        record = {'claim': fact.claim, 'source': fact.source, 'verified_at_observation': fact.verified,
                  'semantic_direction_id': fact.semantic_direction_id,
                  'workspace_dependencies': list(fact.workspace_dependencies),
                  'observed_at_fingerprint': fact.observed_at_fingerprint}
        candidate = [*payload['observed_facts'], record]
        if len(compact(dict(payload, observed_facts=candidate))) + 40 <= max_chars:
            payload['observed_facts'] = candidate
        else:
            payload['omitted_facts'] += 1
    if len(compact(payload)) > max_chars:
        raise ValueError('Memory budget too small for safe metadata')
    return compact(payload)

def context_and_memory(context, rules, *, mode, max_chars, memory_chars=2500, retrieved_count=None):
    if max_chars < 4000 or not 500 <= memory_chars <= max_chars - 1500:
        raise ValueError('Context budget must reserve >=1500 ordinary chars and >=500 memory chars')
    panel = memory_panel(context, rules, mode=mode, max_chars=memory_chars, retrieved_count=retrieved_count)
    ordinary_budget = max_chars - memory_chars
    view = project_context_for_prompt(context, max_chars=ordinary_budget)
    # Existing projector can exceed limits for extreme direction counts. Drop
    # display records only, never graph identities/state; expose the omission count.
    omitted = 0
    view['display_records_omitted'] = 0
    for key in ('facts_and_evidence', 'analysis_and_conclusions', 'incomplete_plans', 'semantic_directions', 'unresolved_issues'):
        while len(compact(view)) > ordinary_budget and view[key]:
            view[key].pop(0)
            omitted += 1
            view['display_records_omitted'] = omitted
    for key in ('environment_summary', 'current_solution', 'task_goal'):
        if len(compact(view)) > ordinary_budget:
            view[key] = clip(view[key], 120)
    if len(compact(view)) > ordinary_budget:
        raise ValueError('Context budget cannot fit minimal structured view')
    return compact(view), panel
