"""Resource-envelope adapter; no baseline search/memory policy changes."""
import json
import math
from pathlib import Path

CONTEXT_TOKENS = 1_000_000
HEADROOM = 65_536
OUTPUT_TOKENS = 32_768
WIRE_LIMIT = 800
HISTORY_UNITS = (CONTEXT_TOKENS - HEADROOM) * 4


def raw_estimate(messages):
    return sum(math.ceil(len(m['content'].encode('utf-16-le')) / 8)
               + (4 if m['role'] == 'system' else 8) for m in messages)


def install(method):
    import client
    if method != 'taco':
        return
    import agents
    import runner
    from common import save
    original_action = agents.action
    original_linear = runner.linear

    def bounded_action(backend, *args, **kwargs):
        result = original_action(backend, *args, **kwargs)
        if result.get('action') == 'run':
            requested = result.get('timeout_seconds')
            if isinstance(requested, bool) or not isinstance(requested, (int, float)) or not math.isfinite(requested):
                effective = 300
            else:
                effective = min(300, max(1, requested))
            if requested != effective:
                save(backend.directory / f'timeout-normalized-{backend.logical:04d}.json',
                     {'effective_seconds': effective, 'model_calls': 0})
                result = dict(result, timeout_seconds=effective)
        return result

    def local_linear(backend, env, instruction, taco=False, cache_path=None):
        return original_linear(backend, env, instruction, taco=taco,
                               cache_path=env.directory / 'taco-rules.json' if taco else cache_path)

    agents.action = bounded_action
    runner.linear = local_linear


def verify_protocol(protocol):
    expected = {'model': 'deepseek-flash', 'temperature': 0, 'max_tokens': OUTPUT_TOKENS,
                'context_tokens': CONTEXT_TOKENS, 'context_headroom_tokens': HEADROOM,
                'actual_api_attempts_per_task': WIRE_LIMIT, 'max_tools': 600,
                'wall_seconds': 7200, 'command_seconds': 300}
    assert all(protocol[k] == v for k, v in expected.items()), 'Resource profile drift'
    assert len(protocol['tasks']) == 7 and protocol['cross_task_memory'] is False
    assert all(r['wall_seconds'] == 7200 for r in protocol['tasks'])
