"""Bounded recovery from repeated decisions; no extra model calls or success claims."""
from collections import OrderedDict


class RepeatRecovery:
    def __init__(self, max_rejections=6, max_unchanged_retries=2):
        self.max_rejections = max_rejections
        self.max_unchanged_retries = max_unchanged_retries
        self.rejections = 0
        self.retries = OrderedDict()

    def decide(self, observation, reason):
        if not observation:
            self.rejections = 0
            return True, None, False
        key = (observation['command_key'], observation['output_sha256'], observation.get('scope_token'))
        used = self.retries.get(key, 0)
        if reason and used < self.max_unchanged_retries:
            self.retries[key] = used + 1
            self.retries.move_to_end(key)
            while len(self.retries) > 16:
                self.retries.popitem(last=False)
            return True, None, False
        self.rejections += 1
        exhausted = self.rejections >= self.max_rejections
        stage = 'strategy_reset' if self.rejections >= 2 else 'repeat_warning'
        notice = {
            'action_not_executed': True, 'decision_advice': observation,
            'recovery_stage': stage, 'consecutive_rejections': self.rejections,
            'remaining_recovery_decisions': max(0, self.max_rejections - self.rejections),
            'unchanged_retries_used': used,
            'instruction': (
                'No new output came from this action. Use the evidence already supplied. '
                'Choose a genuinely different hypothesis, information source, or implementation step; '
                'do not merely rename the same command. State the expected new evidence in purpose. '
                'A concrete retry_reason allows at most two unchanged-output retries. '
                'You may submit the current artifact with honest limitations. '
                'Repeated rejections end as stagnation, never as task success.'),
        }
        return False, notice, exhausted
