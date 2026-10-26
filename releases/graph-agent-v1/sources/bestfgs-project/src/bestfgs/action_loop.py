"""Bounded repetition guard at the last boundary before task execution."""
from collections import OrderedDict
from .lean_memory import action_key


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

    def check(self, action, scope):
        key = (loop_key(action), scope)
        prior = self.observed.get(key)
        if prior is None:
            return None
        # Incomplete capture and declared changing external state can justify
        # one bounded retry. A prose novelty claim alone cannot authorize it.
        retry = action.get('loop_retry')
        allowed = (isinstance(retry, dict) and
                   all(isinstance(retry.get(k), str) and 0 < len(retry[k].strip()) <= 300
                       for k in ('reason', 'expected_change')) and key not in self.retries)
        if allowed:
            self.retries.add(key)
            return None
        return dict(reason='same_command_in_unchanged_workspace', evidence_id=prior['id'],
                    prior_result=prior, retry_used=key in self.retries,
                    instruction='Use the cached result. Make a relevant edit or ask a different question. '
                                'For genuinely changing external state, declare one loop_retry with '
                                'reason and expected_change; repeated claims cannot bypass the bound.')

    def observe(self, action, row):
        # A command that modified the workspace may legitimately be run again.
        if row['before'] != row['after']:
            return
        key = (loop_key(action), row['after'])
        self.observed[key] = {k: row[k] for k in ('id', 'return_code', 'stdout', 'stderr',
                             'timed_out', 'capture_incomplete', 'terminal_projection_incomplete')}
        self.observed.move_to_end(key)
        while len(self.observed) > self.capacity:
            expired, _ = self.observed.popitem(last=False)
            self.retries.discard(expired)
