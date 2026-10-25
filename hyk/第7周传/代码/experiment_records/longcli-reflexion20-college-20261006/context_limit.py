"""Final-envelope byte guard. Official durable compaction owns all history.

Never secretly remove messages or tool results at the provider boundary.
"""
import json

LIMIT = 48000


class InputBudgetExceeded(ValueError):
    pass


def input_bytes(body):
    return len(json.dumps({k: body[k] for k in ('messages', 'tools') if k in body},
                          ensure_ascii=False).encode('utf-8'))


def fit_request(body):
    size = input_bytes(body)
    if size > LIMIT:
        raise InputBudgetExceeded(f'LONGCLI_INPUT_BUDGET: {size} > {LIMIT}; native compaction required')
    return body, {'before_bytes': size, 'after_bytes': size, 'dropped_messages': 0,
                  'input_unit': 'UTF-8 bytes, messages plus native tool declarations',
                  'history_owner': 'Reflexion bounded episodic memory; explicit native evidence clipping'}
