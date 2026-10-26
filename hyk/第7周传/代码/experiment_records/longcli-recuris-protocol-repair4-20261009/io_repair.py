"""Transport/schema recovery only; the author's memory/search kernel is unchanged."""
import json
from client import clip_bytes
from recuris.protocol import ProtocolError, parse_object, parse_action

SCRIPT_BYTES = 524288  # Same shared sandbox stdin capacity, not a token budget.
ACTION_KEYS = {'analysis', 'duration', 'final_answer', 'goal_id', 'keystrokes', 'operation'}

# This constant is executed ONLY through the owned task-container tool driver.
# Programs receive closed stdin rather than consuming subsequent script lines.
SCRIPT_BOOTSTRAP = r'''import os,sys,tempfile,subprocess
script=sys.stdin.read()
with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.sh',dir='/tmp',delete=False) as f:
    f.write(script); path=f.name
try:
    status=subprocess.run(['bash',path],stdin=subprocess.DEVNULL).returncode
finally:
    os.unlink(path)
raise SystemExit(status if status>=0 else 128-status)
'''


def parse_action_io(text, max_duration=300):
    value = parse_object(text)  # Keep duplicate-key/nonfinite/whole-object checks.
    # Explicitly allow only the observed non-executable extra field. Never commit it.
    value.pop('working_state', None)
    if set(value) != ACTION_KEYS:
        missing = sorted(ACTION_KEYS - set(value)); extra = sorted(set(value) - ACTION_KEYS)
        raise ProtocolError(f'Action schema: missing={missing}, unexpected={extra}; return only six required fields')
    script = value['keystrokes']
    if not isinstance(script, str):
        raise ProtocolError('keystrokes must be a string')
    if '\x00' in script:
        raise ProtocolError('keystrokes contains NUL; no command was executed')
    try:
        size = len(script.encode('utf-8'))
    except UnicodeEncodeError as exc:
        raise ProtocolError('keystrokes is not valid UTF-8') from exc
    if size > SCRIPT_BYTES:
        raise ProtocolError(f'keystrokes is {size} UTF-8 bytes; shared stdin capacity is {SCRIPT_BYTES}; split file writes without truncating code')
    if len(script) <= 12000:
        return parse_action(json.dumps(value, ensure_ascii=False), max_duration)
    # Only execute may carry a long script. Native validation still enforces every
    # other field, operation, duration and goal relation. No command is shortened.
    if value['operation'] != 'execute':
        raise ProtocolError('Only execute may contain a nonempty long script')
    parsed = parse_action(json.dumps(dict(value, keystrokes=''), ensure_ascii=False), max_duration)
    parsed['keystrokes'] = script
    return parsed


class ProtocolRecovery:
    def _json(self, messages, purpose, validate):
        base = list(messages); attempt = 0
        while True:
            # Native model/time and shared actual-wire budgets remain authoritative.
            reply = self._complete(messages, purpose)
            attempt += 1
            try:
                if reply.finish_reason == 'length':
                    raise ProtocolError('Truncated generation; return a shorter complete JSON object')
                if purpose == 'act':
                    value = parse_action_io(reply.content, self.config.max_command_duration)
                    if 'working_state' in parse_object(reply.content):
                        self._log('ignored_nonexecution_field', purpose=purpose, fields=['working_state'])
                    return value
                return validate(reply.content)
            except (ProtocolError, KeyError, TypeError) as exc:
                self._log('invalid_response', purpose=purpose, error=str(exc), attempt=attempt,
                          recovery='same shared API/time budget; no tool or state mutation')
                guidance = ('Return exactly analysis, operation, keystrokes, duration, goal_id, final_answer; '
                            'do not return working_state. Escape every newline/quote within JSON strings. '
                            'Long scripts are accepted intact up to the stated shared stdin capacity.'
                            if purpose == 'act' else
                            'Keep the required schema in the system prompt; do not change existing goals or fabricate receipts.')
                # Retain only the latest bad proposal; avoid an ever-growing repair transcript.
                messages = [*base,
                    {'role': 'assistant', 'content': clip_bytes(reply.content, 2000)},
                    {'role': 'user', 'content': f'Protocol error: {exc}. {guidance} '
                     'No proposed actions or state changes were applied. Correct the JSON only.'}]
