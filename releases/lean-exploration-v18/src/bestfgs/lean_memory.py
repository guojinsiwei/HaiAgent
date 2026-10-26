"""Task-local, evidence-linked advice. Conditions remain hypotheses, not hard bans."""
from collections import OrderedDict
import re
from .lean_protocol import text
from .lean_progress import normalize_workspace_path


def tokens(value):
    return set(re.findall(r'[\w.-]+', value.lower()))


class Memories:
    def __init__(self, capacity=24):
        self.capacity = capacity
        self.items = OrderedDict()
        self.next_id = 1

    def admit(self, value, evidence, advertised, dependency_state):
        if not isinstance(value, dict):
            raise ValueError('memory must be an object')
        conclusion = text(value.get('conclusion'), 'conclusion', 500)
        condition = text(value.get('condition'), 'condition', 400)
        kind = value.get('kind', 'finding')
        if kind not in {'finding', 'blocker', 'procedure'}:
            raise ValueError('unsupported memory kind')
        operation = value.get('operation', '')
        if operation:
            operation = text(operation, 'operation', 120)
        next_step = value.get('next_step', '')
        if next_step:
            next_step = text(next_step, 'next_step', 400)
        raw_targets = value.get('targets', [])
        if not isinstance(raw_targets, list) or len(raw_targets) > 4:
            raise ValueError('memory targets must be a list of at most four paths')
        targets = []
        for target in raw_targets:
            normalized = normalize_workspace_path(target)
            if normalized not in targets:
                targets.append(normalized)
        ids = value.get('evidence_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 3 or any(
                not isinstance(e, str) or e not in advertised or e not in evidence for e in ids):
            raise ValueError('memory requires visible real evidence')
        for record in self.items.values():
            if (record['conclusion'], record['condition'], record['kind'], record['operation'],
                    record['targets'], record['next_step'], record['evidence_ids']) == (
                    conclusion, condition, kind, operation, targets, next_step, ids):
                return record, False
        item = dict(id='M' + str(self.next_id), conclusion=conclusion, condition=condition,
                    kind=kind, operation=operation, targets=targets, next_step=next_step,
                    evidence_ids=ids, scope=evidence[ids[-1]]['after'],
                    evidence_scopes=sorted({evidence[key]['after'] for key in ids}),
                    dependency_state=dependency_state(targets) if targets else {},
                    status='evidence_linked_model_claim')
        self.next_id += 1
        self.items[item['id']] = item
        while len(self.items) > self.capacity:
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
            applicability = self.applicability(item, scope, current_dependencies)
            current = 'unchanged' in applicability or applicability.startswith('same_workspace')
            scored.append(((overlap, current, index), dict(item, applicability=applicability)))
        return [item for _, item in sorted(scored, key=lambda row: row[0], reverse=True)[:limit]]

    def match_action(self, action, scope, current_dependencies, limit=2):
        if action.get('action') != 'run':
            return []
        query = ' '.join([*action.get('argv', []), action.get('cwd', '.'), action.get('purpose', '')]).lower()
        query_tokens = tokens(query)
        matches = []
        for index, item in enumerate(self.items.values()):
            applicability = self.applicability(item, scope, current_dependencies)
            current = 'unchanged' in applicability or applicability.startswith('same_workspace')
            target_hit = any(target.lower() in query or target.rsplit('/', 1)[-1].lower() in query
                             for target in item['targets'])
            operation_tokens = tokens(item['operation'])
            operation_hit = bool(operation_tokens and operation_tokens.issubset(query_tokens))
            semantic_tokens = tokens(item['conclusion'] + ' ' + item['condition'] + ' ' + item['next_step'])
            overlap = len(query_tokens & semantic_tokens)
            high = current and (target_hit or operation_hit or overlap >= 3)
            if high:
                score = 8*int(target_hit) + 5*int(operation_hit) + overlap
                matches.append(((score, index), dict(item, applicability=applicability,
                    match_reasons={'target': target_hit, 'operation': operation_hit,
                                   'semantic_token_overlap': overlap})))
        return [item for _, item in sorted(matches, key=lambda row: row[0], reverse=True)[:limit]]
