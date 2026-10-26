"""Bounded repetition evidence and a model-declared exploration ledger.

Exact command repetition is objective.  Strategy identity is deliberately weaker:
it is the policy model's stable label for an approach, not a host claim that two
arbitrary commands are semantically equivalent.  Keeping the two notions separate
lets the runtime ask for a new direction without pretending to solve semantic
similarity from shell text.
"""
import hashlib
import json
import re
from collections import OrderedDict


_TRANSIENT_PATH = re.compile(r"(?<![\w.-])(?:/tmp|/var/tmp)/[A-Za-z0-9_.-]+")


def observation_fingerprint(exit_code, output, error, test_status):
    """Fingerprint observations while removing only incidental temp filenames."""
    normalized = [_TRANSIENT_PATH.sub('/tmp/__HAI_TMP__', str(value or ''))
                  for value in (output, error, test_status)]
    return hashlib.sha256(json.dumps([exit_code, *normalized],
                                     ensure_ascii=False).encode()).hexdigest()


def command_key(command, cwd, input_digest):
    return hashlib.sha256(json.dumps([command, cwd, input_digest]).encode()).hexdigest()


class RepetitionTracker:
    def __init__(self, capacity=16, threshold=3):
        self.capacity, self.threshold = capacity, threshold
        self.entries = OrderedDict()
        self.scope = None

    def set_scope(self, cwd, workspace, environment):
        scope = (cwd, workspace, environment)
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
                'evidence_ids': ((old['evidence_ids'][-1:] if old and count > 1 else []) + [evidence_id]),
                'scope_verified': event.workspace is not None and event.environment is not None}
        self.entries[key] = item
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return dict(item) if count >= self.threshold else None

    def lookup(self, command, cwd, input_digest):
        item = self.entries.get(command_key(command, cwd, input_digest))
        return dict(item) if item and item['count'] >= self.threshold else None


class DirectionLedger:
    """Host-derived semantic-direction ledger with conservative stall evidence.

    A direction is stalled only after repeated identical observations or a long
    no-workspace-change diagnostic streak. Different output is retained as new
    evidence; a direction label alone never proves failure.
    """

    def __init__(self, capacity=12, repeat_threshold=3, diagnostic_threshold=8):
        if min(capacity, repeat_threshold, diagnostic_threshold) <= 0:
            raise ValueError('direction limits must be positive')
        self.capacity = capacity
        self.repeat_threshold = repeat_threshold
        self.diagnostic_threshold = diagnostic_threshold
        self.entries = OrderedDict()
        self.serial = 0

    def observe(self, event, evidence_id, output_sha256, outcome):
        if not event.direction_key:
            return None
        item = self.entries.pop(event.direction_key, None)
        prior_status = item.get('status') if item else None
        if item is None:
            self.serial += 1
            item = {'id': f'D{self.serial}', 'direction_key': event.direction_key,
                    'summary': event.direction_summary or 'host-derived direction',
                    'targets': list(event.direction_targets), 'attempts': 0,
                    'workspace_changes': 0, 'no_change_streak': 0,
                    'repeated_evidence': 0, 'unique_observations': 0,
                    'observation_sha256': [],
                    'evidence_ids': [], 'outcomes': {}, 'status': 'active',
                    'last_output_sha256': None}
        changed = (event.workspace_before is not None and
                   event.workspace_before != event.workspace)
        repeated = bool(output_sha256 and output_sha256 == item['last_output_sha256'])
        item['attempts'] += 1
        item['workspace_changes'] += int(changed)
        item['no_change_streak'] = 0 if changed else item['no_change_streak'] + 1
        item['repeated_evidence'] = item['repeated_evidence'] + 1 if repeated and not changed else 0
        observations = (item.get('observation_sha256', []) +
                        ([output_sha256] if output_sha256 else []))[-self.diagnostic_threshold:]
        item['observation_sha256'] = observations
        item['unique_observations'] = len(set(observations))
        item['last_output_sha256'] = output_sha256
        item['evidence_ids'] = (item['evidence_ids'] + [evidence_id])[-3:]
        item['outcomes'][outcome] = item['outcomes'].get(outcome, 0) + 1
        if item['repeated_evidence'] >= self.repeat_threshold - 1:
            item['status'] = 'stalled_semantic_repeat'
        elif (item['no_change_streak'] >= self.diagnostic_threshold and
              item['unique_observations'] <= 2):
            # Reading/searching is allowed to make epistemic progress without
            # mutating the workspace.  Only a long low-information cycle stalls;
            # a stream of distinct observations remains active exploration.
            item['status'] = 'stalled_low_information_cycle'
        elif changed:
            item['status'] = 'changed_workspace_unverified'
        else:
            item['status'] = 'active'
        item['newly_stalled'] = item['status'].startswith('stalled_') and not (
            isinstance(prior_status, str) and prior_status.startswith('stalled_'))
        self.entries[event.direction_key] = item
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return json.loads(json.dumps(item, ensure_ascii=False))

    def lookup(self, direction_key):
        item = self.entries.get(direction_key)
        return json.loads(json.dumps(item, ensure_ascii=False)) if item else None

    def snapshot(self, limit=None):
        values = list(self.entries.values())
        if limit is not None:
            values = values[-limit:]
        return json.loads(json.dumps(values, ensure_ascii=False))


def advice(item):
    if not item:
        return None
    return dict(item) | {
        'observation': 'This exact action returned identical captured output repeatedly. No new output was observed; this is not proof that all environment state is unchanged.',
        'next_decision': 'Prefer a different information source or method. If repeating is necessary, supply retry_reason explaining the expected change or bounded polling/revalidation need. Do not merely say try again.',
    }


def normalize_strategy(label):
    """Normalize an explicit model label; never infer equivalence across labels."""
    if not isinstance(label, str):
        raise ValueError("strategy must be text")
    value = re.sub(r"\s+", " ", label.strip())
    if not 3 <= len(value) <= 200:
        raise ValueError("strategy must contain 3..200 characters")
    return value.casefold(), value


def normalize_subgoal(label):
    """Normalize a model-declared rolling focus, without judging completion."""
    if not isinstance(label, str):
        raise ValueError("subgoal must be text")
    value = re.sub(r"\s+", " ", label.strip())
    if not 3 <= len(value) <= 160:
        raise ValueError("subgoal must contain 3..160 characters")
    return value.casefold(), value


class SubgoalLedger:
    """Bounded, observational progress scaffold with no planner/model calls.

    The policy declares only its current focus.  The host records attempts and
    evidence; it never upgrades a focus to "completed" from a model assertion or
    exit code.  Switching focus therefore means "suspended", not "done".
    """

    def __init__(self, capacity=6):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("subgoal capacity must be positive")
        self.capacity = capacity
        self.entries = OrderedDict()
        self.serial = 0
        self.active_key = None

    def observe(self, label, strategy, evidence_id, outcome, *, workspace_changed=False,
                repeated_output=False):
        key, display = normalize_subgoal(label)
        if self.active_key is not None and self.active_key != key:
            previous = self.entries.get(self.active_key)
            if previous is not None and previous["status"] == "active":
                previous["status"] = "suspended_unverified"
        item = self.entries.pop(key, None)
        if item is None:
            self.serial += 1
            item = {"id": f"G{self.serial}", "subgoal": display, "attempts": 0,
                    "strategies": [], "outcomes": {}, "workspace_changes": 0,
                    "repeat_stalls": 0, "evidence_ids": [], "status": "active"}
        item["attempts"] += 1
        item["outcomes"][outcome] = item["outcomes"].get(outcome, 0) + 1
        item["workspace_changes"] += int(bool(workspace_changed))
        item["repeat_stalls"] += int(bool(repeated_output))
        item["evidence_ids"] = (item["evidence_ids"] + [evidence_id])[-3:]
        if strategy and strategy not in item["strategies"]:
            item["strategies"] = (item["strategies"] + [strategy])[-3:]
        item["status"] = "stalled_exact_repeat" if repeated_output else "active"
        self.entries[key] = item
        self.active_key = key
        while len(self.entries) > self.capacity:
            evicted, _ = self.entries.popitem(last=False)
            if evicted == self.active_key:
                self.active_key = None
        return json.loads(json.dumps(item, ensure_ascii=False))

    def mark_stalled(self, label, evidence_ids=()):
        key, display = normalize_subgoal(label)
        item = self.entries.pop(key, None)
        if item is None:
            self.serial += 1
            item = {"id": f"G{self.serial}", "subgoal": display, "attempts": 0,
                    "strategies": [], "outcomes": {}, "workspace_changes": 0,
                    "repeat_stalls": 0, "evidence_ids": [], "status": "active"}
        item["repeat_stalls"] += 1
        item["evidence_ids"] = (item["evidence_ids"] + list(evidence_ids))[-3:]
        item["status"] = "stalled_exact_repeat"
        self.entries[key] = item
        self.active_key = key
        while len(self.entries) > self.capacity:
            evicted, _ = self.entries.popitem(last=False)
            if evicted == self.active_key:
                self.active_key = None
        return json.loads(json.dumps(item, ensure_ascii=False))

    def snapshot(self, limit=None):
        values = list(self.entries.values())
        if limit is not None:
            values = values[-limit:]
        return json.loads(json.dumps(values, ensure_ascii=False))


class StrategyLedger:
    """A bounded task-local account of approaches the policy says it is trying.

    The ledger reports observations only: attempts, outcomes, workspace change and
    exact-repeat stalls.  Workspace change is not labelled task progress, and a
    renamed strategy is not automatically merged with an earlier one.
    """

    def __init__(self, capacity=8):
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("strategy capacity must be positive")
        self.capacity = capacity
        self.entries = OrderedDict()
        self.serial = 0

    def observe(self, label, evidence_id, outcome, *, workspace_changed=False,
                repeated_output=False, note=""):
        key, display = normalize_strategy(label)
        item = self.entries.pop(key, None)
        if item is None:
            self.serial += 1
            item = {"id": f"S{self.serial}", "strategy": display, "attempts": 0,
                    "outcomes": {}, "workspace_changes": 0, "repeat_stalls": 0,
                    "evidence_ids": [], "status": "observed", "last_note": ""}
        item["attempts"] += 1
        item["outcomes"][outcome] = item["outcomes"].get(outcome, 0) + 1
        item["workspace_changes"] += int(bool(workspace_changed))
        item["repeat_stalls"] += int(bool(repeated_output))
        item["evidence_ids"] = (item["evidence_ids"] + [evidence_id])[-3:]
        item["last_note"] = str(note).strip()[:240]
        item["status"] = ("stalled_exact_repeat" if repeated_output else
                          "changed_workspace_unverified" if workspace_changed else "observed")
        self.entries[key] = item
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return json.loads(json.dumps(item, ensure_ascii=False))

    def mark_stalled(self, label, evidence_ids=()):
        key, display = normalize_strategy(label)
        item = self.entries.pop(key, None)
        if item is None:
            self.serial += 1
            item = {"id": f"S{self.serial}", "strategy": display, "attempts": 0,
                    "outcomes": {}, "workspace_changes": 0, "repeat_stalls": 0,
                    "evidence_ids": [], "status": "observed", "last_note": ""}
        item["repeat_stalls"] += 1
        item["evidence_ids"] = (item["evidence_ids"] + list(evidence_ids))[-3:]
        item["status"] = "stalled_exact_repeat"
        item["last_note"] = "Exact action produced identical captured output repeatedly."
        self.entries[key] = item
        while len(self.entries) > self.capacity:
            self.entries.popitem(last=False)
        return json.loads(json.dumps(item, ensure_ascii=False))

    def snapshot(self, limit=None):
        values = list(self.entries.values())
        if limit is not None:
            values = values[-limit:]
        return json.loads(json.dumps(values, ensure_ascii=False))
