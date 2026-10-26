"""Task-local, evidence-linked advice. Conditions remain hypotheses, not hard bans."""
from collections import OrderedDict
import re
import hashlib
import json
import shlex
from .lean_protocol import text, validate_evidence_ids
from .lean_progress import normalize_workspace_path


def tokens(value):
    return set(re.findall(r'[\w.-]+', value.lower()))


def optional_text(value, name, limit, repairs):
    if not isinstance(value, str) or '\x00' in value:
        raise ValueError('invalid ' + name)
    if len(value) > limit:
        # Never turn a truncated instruction into a matching/behavior rule.
        repairs.append(dict(field=name, reason='overlong_optional_field_omitted',
            original_chars=len(value), sha256=hashlib.sha256(value.encode()).hexdigest()))
        return ''
    return value.strip()


class Memories:
    def __init__(self, capacity=24, reliable=False):
        self.capacity = capacity
        self.reliable = reliable
        self.items = OrderedDict()
        self.next_id = 1
        self.evicted = []

    def admit(self, value, evidence, advertised, dependency_state, *, current_scope=None):
        if not isinstance(value, dict):
            raise ValueError('memory must be an object')
        conclusion = text(value.get('conclusion'), 'conclusion', 500)
        condition = text(value.get('condition'), 'condition', 400)
        kind = value.get('kind', 'finding')
        if not isinstance(kind, str) or kind not in {'finding', 'blocker', 'procedure'}:
            raise ValueError('unsupported memory kind')
        repairs = []
        operation = optional_text(value.get('operation', ''), 'operation', 120, repairs)
        next_step = optional_text(value.get('next_step', ''), 'next_step', 400, repairs)
        raw_targets = value.get('targets', [])
        if not isinstance(raw_targets, list) or len(raw_targets) > 4:
            raise ValueError('memory targets must be a list of at most four paths')
        targets = []
        for target in raw_targets:
            normalized = normalize_workspace_path(target)
            if normalized not in targets:
                targets.append(normalized)
        ids = validate_evidence_ids(value.get('evidence_ids'), set(advertised).intersection(evidence), minimum=1)
        deps = dependency_state(targets) if targets else {}
        if self.reliable and targets:
            snapshots = [evidence[key].get('stable_dependencies', {}) for key in ids]
            # File anchors must come from execution time, not retrospectively from changed files.
            deps = {target: snapshots[-1].get(target, 'unknown') for target in targets}
            for target in targets:
                if any(s.get(target, 'unknown') != deps[target] for s in snapshots):
                    deps[target] = 'unknown'
                if deps[target] == 'unknown' and current_scope and all(evidence[k]['after']==current_scope for k in ids):
                    deps[target] = dependency_state([target]).get(target, 'unknown')
                if not str(deps[target]).startswith(('file:', 'dir:', 'missing')):
                    deps[target] = 'unknown'
        for record in self.items.values():
            if self.reliable and (record['conclusion'].casefold(), record['condition'].casefold(), record['kind'],
                    record['targets'], record['dependency_state'], record['scope'] if not targets else None) == (
                    conclusion.casefold(), condition.casefold(), kind, targets, deps,
                    evidence[ids[-1]]['after'] if not targets else None):
                record['evidence_ids'] = list(dict.fromkeys(record['evidence_ids']+ids))[-3:]
                record['reinforcements'] = record.get('reinforcements', 1)+1
                record['updated_at'] = self.next_id
                return record, False
            if (record['conclusion'], record['condition'], record['kind'], record['operation'],
                    record['targets'], record['next_step'], record['evidence_ids']) == (
                    conclusion, condition, kind, operation, targets, next_step, ids):
                return record, False
        item = dict(id='M' + str(self.next_id), conclusion=conclusion, condition=condition,
                    kind=kind, operation=operation, targets=targets, next_step=next_step,
                    evidence_ids=ids, scope=evidence[ids[-1]]['after'],
                    evidence_scopes=sorted({evidence[key]['after'] for key in ids}),
                    dependency_state=deps, repairs=repairs,
                    status='evidence_linked_model_claim', reinforcements=1, updated_at=self.next_id)
        self.next_id += 1
        self.items[item['id']] = item
        while len(self.items) > self.capacity:
            if self.reliable:
                current = dependency_state(self.dependency_targets())
                def value(record):
                    applies = self.applicability(record, current_scope or evidence[ids[-1]]['after'], current)
                    valid = 'unchanged' in applies or applies.startswith('same_workspace')
                    return (valid, min(record.get('reinforcements',1),3), record.get('updated_at',0))
                victim = min(self.items, key=lambda key: value(self.items[key]))
                self.evicted.append(dict(id=victim, reason='bounded_validity_reinforcement_recency'))
                del self.items[victim]
            else:
                self.items.popitem(last=False)
        return item, True

    def dependency_targets(self):
        return sorted({target for item in self.items.values() for target in item['targets']})

    @staticmethod
    def applicability(item, scope, current_dependencies):
        if item['targets']:
            current = {target: current_dependencies.get(target, 'unknown') for target in item['targets']}
            same = current == item['dependency_state'] and 'unknown' not in current.values()
            return ('target_dependencies_unchanged_external_state_unverified' if same
                    else 'target_dependencies_changed_or_unknown_recheck_required')
        same = all(s == scope for s in item['evidence_scopes'])
        return ('same_workspace_external_state_unverified' if same
                else 'historical_recheck_required')

    def recall(self, query, scope, current_dependencies, limit=4):
        query_tokens = tokens(query)
        scored = []
        for index, item in enumerate(self.items.values()):
            words = tokens(' '.join((item['conclusion'], item['condition'], item['operation'],
                                      item['next_step'], *item['targets'])))
            overlap = len(query_tokens & words)
            if self.reliable and overlap == 0:
                continue
            applicability = self.applicability(item, scope, current_dependencies)
            current = 'unchanged' in applicability or applicability.startswith('same_workspace')
            key = ((current, overlap, min(item.get('reinforcements',1),3), index) if self.reliable
                   else (overlap, current, index))
            scored.append((key, dict(item, applicability=applicability)))
        return [item for _, item in sorted(scored, key=lambda row: row[0], reverse=True)[:limit]]

    def match_action(self, action, scope, current_dependencies, limit=2):
        if action.get('action') != 'run':
            return []
        query = ' '.join([*action.get('argv', []), action.get('cwd', '.'), action.get('purpose', '')]).lower()
        query_tokens = tokens(query)
        matches = []
        for index, item in enumerate(self.items.values()):
            if self.reliable and item['kind'] != 'blocker':
                continue
            applicability = self.applicability(item, scope, current_dependencies)
            current = 'unchanged' in applicability or applicability.startswith('same_workspace')
            target_hit = any(target.lower() in query or target.rsplit('/', 1)[-1].lower() in query
                             for target in item['targets'])
            operation_tokens = tokens(item['operation'])
            operation_hit = bool(operation_tokens and operation_tokens.issubset(query_tokens))
            semantic_tokens = tokens(item['conclusion'] + ' ' + item['condition'] + ' ' + item['next_step'])
            overlap = len(query_tokens & semantic_tokens)
            exact = item.get('command_key') == action_key(action) if item.get('command_key') else False
            high = current and ((exact or operation_hit and (target_hit or overlap >= 3))
                                if self.reliable else (target_hit or operation_hit or overlap >= 3))
            if high:
                score = 8*int(target_hit) + 5*int(operation_hit) + overlap
                matches.append(((score, index), dict(item, applicability=applicability,
                    match_reasons={'target': target_hit, 'operation': operation_hit,
                                   'semantic_token_overlap': overlap})))
        return [item for _, item in sorted(matches, key=lambda row: row[0], reverse=True)[:limit]]


_SHELL_WORDS = frozenset('if then else elif fi for while until do done case esac in function select time coproc ! { } [[ ]]'.split())


def _literal_shell_identity(command):
    """Normalize ONE static simple command, not arbitrary shell programs.

    shlex is a lexer, not a shell parser. First reject expansion/control syntax.
    Preserve the command word's quoting (which can suppress alias expansion),
    and preserve every argument's literal whitespace and order. Unsupported or
    malformed programs retain their original identity; never rewrite execution.
    """
    if any(c in command for c in '\n\r\x00$`'):
        return None
    source = command.lstrip(' \t')
    quote, first_end, i = None, None, 0
    while i < len(source):
        char = source[i]
        if quote == "'":
            if char == "'": quote = None
        elif quote == '"':
            if char == '"': quote = None
            elif char == '\\': i += 1
        elif char in "'\"":
            quote = char
        elif char == '\\':
            i += 1
        elif char in ' \t':
            if first_end is None: first_end = i
        elif char in '#~*?[]{}()!;&|<>':
            return None
        i += 1
    if quote is not None:
        return None
    try:
        words = shlex.split(source, comments=False, posix=True)
    except ValueError:
        return None
    if not words or not words[0] or words[0] in _SHELL_WORDS or '=' in words[0]:
        return None
    # Do not merge `python` with `"python"`: aliases may behave differently.
    program_spelling = source[:first_end if first_end is not None else len(source)]
    return dict(literal_shell_v1=[program_spelling, words[1:]])


def action_key(action):
    # Purpose/uses_memory are not command identity; stdin and cwd are.
    # Direct argv is already tokenized: spaces inside its elements are data.
    argv = action.get('argv')
    if (isinstance(argv, list) and len(argv) == 3
            and argv[0].rsplit('/',1)[-1] in {'bash','sh'} and argv[1] in {'-c','-lc'}):
        identity = _literal_shell_identity(argv[2])
        if identity is not None:
            argv = [argv[0], argv[1], identity]
    value = [argv, action.get('cwd','.'), action.get('stdin') or '']
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
