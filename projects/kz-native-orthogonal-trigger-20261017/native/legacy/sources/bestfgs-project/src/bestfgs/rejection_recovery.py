"""One rescue per unresolved blockage; rejection counts never end a task."""
from .lean_audit import digest


def known(state):
    return isinstance(state, str) and state not in ('unknown', 'other') and not state.startswith('link:')


def changed_paths(before, after):
    return [p for p, old in before.items() if known(old) and known(after.get(p))
            and old != after[p]]


class RejectionRecovery:
    def __init__(self, limit=7):
        self.limit = limit
        self.streak = 0
        self.advisor_attempted = False
        self.advisor_due = False
        self.targets = {}
        self.seen = set()
        self.generation = 0

    def reject(self, dependencies):
        for path, state in dependencies.items():
            if known(state):
                self.targets.setdefault(path, state)
        self.streak += 1
        if self.streak >= self.limit and not self.advisor_attempted:
            self.advisor_due = True

    def advisor_started(self):
        self.advisor_attempted = True
        self.advisor_due = False
        self.streak = 0

    def observe(self, row, *, informative=False):
        signature = digest([row.get('return_code'), row.get('stdout'), row.get('stderr')])
        novel = signature not in self.seen
        self.seen.add(signature)
        relevant = set(row.get('relevant_dependencies', {})) & set(self.targets)
        complete = not any(row.get(k) for k in
                           ('capture_incomplete', 'terminal_projection_incomplete', 'timed_out', 'blocked'))
        changes = changed_paths(self.targets, row.get('dependency_after', {}))
        new_evidence = (complete and novel and informative and bool(relevant)
                        and bool((row.get('stdout', '') + row.get('stderr', '')).strip()))
        if self.streak or self.advisor_attempted or self.advisor_due:
            if changes or new_evidence:
                reason = 'observed_relevant_change' if changes else 'new_relevant_evidence'
                self.streak = 0
                self.advisor_attempted = self.advisor_due = False
                self.targets = {}
                self.generation += 1
                return dict(reason=reason, changed_paths=changes, evidence_id=row['id'])
        return None

    def view(self):
        return dict(rejections=self.streak, limit=self.limit,
                    phase='after_advisor' if self.advisor_attempted else 'before_advisor',
                    advisor_due=self.advisor_due, hard_stop_enabled=False,
                    targets=sorted(self.targets), generation=self.generation)
