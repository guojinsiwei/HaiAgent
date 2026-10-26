"""Bounded observations of repeated output, not a proof of semantic redundancy."""
import hashlib
import json
from collections import OrderedDict


def command_key(command, cwd, input_digest):
    return hashlib.sha256(json.dumps([command, cwd, input_digest]).encode()).hexdigest()


class RepetitionTracker:
    def __init__(self, capacity=16, threshold=3):
        self.capacity, self.threshold = capacity, threshold
        self.entries = OrderedDict()
        self.scope = None

    def set_scope(self, cwd, workspace, environment):
        # cwd already belongs to each command key. Merely projecting context at
        # the workspace root must not erase observations made in a subdirectory.
        scope = (workspace, environment)
        if self.scope is not None and scope != self.scope:
            self.entries.clear()
        self.scope = scope

    def observe(self, event, evidence_id, complete):
        self.set_scope(event.cwd, event.workspace, event.environment)
        key = command_key(event.command, event.cwd, event.input_digest)
        old = self.entries.pop(key, None)
        if (not complete or event.timed_out or event.blocked or event.exit_code is None
                or event.workspace_before is not None and event.workspace_before != event.workspace):
            return None
        fingerprint = hashlib.sha256(json.dumps(
            [event.exit_code, event.stdout, event.stderr], ensure_ascii=False).encode()).hexdigest()
        count = old['count'] + 1 if old and old['output_sha256'] == fingerprint else 1
        item = {'command_key': key, 'output_sha256': fingerprint, 'count': count,
                'scope_token': hashlib.sha256(json.dumps(self.scope).encode()).hexdigest(),
                'evidence_ids': ((old['evidence_ids'][-1:] if old and count > 1 else []) + [evidence_id]),
                'scope_verified': event.workspace is not None and event.environment is not None}
        self.entries[key] = item
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return dict(item) if count >= self.threshold else None

    def lookup(self, command, cwd, input_digest):
        item = self.entries.get(command_key(command, cwd, input_digest))
        return dict(item) if item and item['count'] >= self.threshold else None


def advice(item):
    if not item:
        return None
    return dict(item) | {
        'observation': 'This exact action returned identical captured output repeatedly. No new output was observed; this is not proof that all environment state is unchanged.',
        'next_decision': 'Prefer a different information source or method. If repeating is necessary, supply retry_reason explaining the expected change or bounded polling/revalidation need. Do not merely say try again.',
    }
