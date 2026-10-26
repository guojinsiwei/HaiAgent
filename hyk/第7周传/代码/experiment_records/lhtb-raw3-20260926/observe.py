"""Read-only cycle candidates, never a semantic redundancy or success verdict."""
import argparse
import hashlib
import json
from pathlib import Path

def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def analyze(path):
    starts, calls = {}, []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row['event'] == 'tool_start':
            starts[row['call_id']] = row
        if row['event'] != 'tool_end':
            continue
        start, result = starts[row['call_id']], row['result']
        command = start['command']
        before, after = start.get('before_revision'), row.get('after_revision')
        complete = not any(result.get(k) for k in ('timed_out', 'blocked', 'output_truncated'))
        calls.append({'id': row['call_id'], 'command': command['argv'],
                      'stable_workspace': before is not None and before == after,
                      'complete': complete, 'key': signature({
                          'argv': command['argv'], 'cwd': command.get('cwd'), 'stdin': command.get('stdin'),
                          'stdout': result.get('stdout_sha256') or result.get('stdout'),
                          'stderr': result.get('stderr_sha256') or result.get('stderr'),
                          'exit_code': result.get('exit_code')})})
    candidates = []
    for width in range(1, 5):
        repeats = 5 if width == 1 else 3
        length = width * repeats
        last_end = -1
        for end in range(length, len(calls) + 1):
            block = calls[end-length:end]
            if not all(c['complete'] for c in block):
                continue
            keys = [c['key'] for c in block]
            if keys != keys[:width] * repeats or (width > 1 and len(set(keys[:width])) == 1):
                continue
            if last_end == end - 1:
                candidates[-1]['last_call'] = block[-1]['id']
            else:
                candidates.append({'period': width, 'first_call': block[0]['id'], 'last_call': block[-1]['id'],
                    'commands': [c['command'] for c in block[:width]],
                    'initial_window_workspace_unchanged': all(c['stable_workspace'] for c in block),
                    'verdict': 'candidate only: manually exclude legitimate polling/revalidation and inspect semantic progress'})
            last_end = end
    return {'trace': str(path), 'tool_calls': len(calls), 'cycle_candidates': candidates,
            'semantic_redundancy_rate': None, 'official_success': None,
            'limitations': 'Misses semantically equivalent commands/different outputs; filesystem evidence excludes external services; 3 tasks cannot estimate benchmark-wide loop prevalence.'}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    print(json.dumps([analyze(p) for p in args.root.glob('**/haia-run/events.jsonl')], indent=2))
