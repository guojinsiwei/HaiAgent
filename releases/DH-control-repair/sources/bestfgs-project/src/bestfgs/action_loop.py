"""Bounded repetition guard at the last boundary before task execution."""
from collections import OrderedDict
from .lean_memory import action_key
from .rejection_recovery import known


def loop_key(action):
    argv = action.get('argv', [])
    if (len(argv) == 3 and argv[0].rsplit('/', 1)[-1] in {'bash', 'sh'}
            and argv[1] in {'-c', '-lc'}):
        script = argv[2]
        # Preserve data in quotes, heredocs, expansions, escapes and newlines.
        # For plain compound commands only, collapse unquoted horizontal space.
        if not any(marker in script for marker in ('<<', '$', '`', '\\', '\n', '\r', '#')):
            out, quote, space = [], None, False
            for ch in script:
                if quote:
                    out.append(ch)
                    if ch == quote: quote = None
                elif ch in ('"', "'"):
                    if space and out: out.append(' ')
                    space = False; quote = ch; out.append(ch)
                elif ch in (' ', '\t'):
                    space = True
                else:
                    if space and out: out.append(' ')
                    space = False; out.append(ch)
            action = dict(action, argv=[argv[0], argv[1], ''.join(out)])
    return action_key(action)


class ActionLoopGuard:
    def __init__(self, capacity=48):
        self.capacity = capacity
        self.observed = OrderedDict()
        self.retries = set()
        self.condition_retries = {}

    def retry_reason(self, action, scope, dependencies=None):
        """Inspect a bounded exemption; spend it only at final dispatch."""
        command = loop_key(action)
        for key, prior in reversed(self.observed.items()):
            if key != (command, scope):
                continue
            used = self.condition_retries.get(key, set())
            timeout = action.get('timeout_seconds',60)
            if (prior.get('timed_out') and type(timeout) is int
                    and timeout > prior.get('timeout_seconds',60) and 'timeout_increase' not in used):
                return 'timeout_increase'
            retry = action.get('loop_retry')
            if (isinstance(retry,dict) and 'external_recheck' not in used
                    and all(isinstance(retry.get(k),str) and 1 <= len(retry[k].strip()) <= 400
                            for k in ('reason','expected_change'))):
                return 'external_recheck'
            return None
        return None

    def tracked_paths(self, action):
        command = loop_key(action)
        return list(dict.fromkeys(p for (key, _), prior in self.observed.items()
                                  if key == command for p in prior.get('dependencies', {})))

    def check(self, action, scope, dependencies=None):
        command = loop_key(action)
        for key, prior in reversed(self.observed.items()):
            if key[0] != command:
                continue
            # Selected dependency lists are not a complete dependency oracle.
            # A changed whole workspace cannot be declared unchanged from them.
            if key[1] != scope:
                continue
            previous = prior.get('dependencies', {})
            if previous:
                if dependencies is None or any(dependencies.get(p) != v for p, v in previous.items()):
                    continue
            reason = self.retry_reason(action, scope, dependencies)
            if reason:
                self.condition_retries.setdefault(key,set()).add(reason)
                return None
            incomplete = prior.get('capture_incomplete') or prior.get('terminal_projection_incomplete')
            if incomplete and key not in self.retries:
                self.retries.add(key)
                return None
            return dict(reason='same_command_in_unchanged_workspace', evidence_id=prior['id'],
                        prior_result=prior, retry_used=key in self.retries,
                        instruction='Use the cached result. Retry after an observed change to related '
                                    'code, dependencies or configuration, or obtain new evidence first. '
                                    'One increased-timeout retry after an observed timeout, or one explicit '
                                    'loop_retry(reason, expected_change) per unchanged state is allowed. '
                                    'An external recheck is unverified, not proof of progress.')
        return None

    def observe(self, action, row):
        # A command that modified the workspace may legitimately be run again.
        dependencies = row.get('relevant_dependencies', {})
        if dependencies:
            if any(row.get('dependency_before', {}).get(p) != v for p, v in dependencies.items()):
                return
        elif row['before'] != row['after']:
            return
        key = (loop_key(action), row['after'])
        self.observed[key] = {k: row[k] for k in ('id', 'return_code', 'stdout', 'stderr',
                             'timed_out', 'capture_incomplete', 'terminal_projection_incomplete')}
        self.observed[key]['dependencies'] = {
            p: v for p, v in row.get('relevant_dependencies', {}).items() if known(v)
        }
        self.observed[key]['timeout_seconds'] = action.get('timeout_seconds',60)
        self.observed.move_to_end(key)
        while len(self.observed) > self.capacity:
            expired, _ = self.observed.popitem(last=False)
            self.retries.discard(expired)
            self.condition_retries.pop(expired,None)
