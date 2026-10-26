"""Print a saved, redacted final prompt; never contact a provider."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('events', type=Path)
    parser.add_argument('--role', default='action', choices=['action','advisor','monitor'])
    parser.add_argument('--request', type=int, help='1-based request for this role; default last')
    parser.add_argument('--attempt', type=int, help='wire retry attempt within the chosen logical request')
    args = parser.parse_args()
    selected, count, wires = None, 0, []
    for line in args.events.open(encoding='utf-8'):
        row = json.loads(line)
        if row.get('role') != args.role: continue
        if row['event'] == 'final_prompt':
            count += 1
            if args.request is None or count == args.request:
                selected = row; wires = []
            elif args.request and count > args.request:
                break
        elif row['event'] == 'wire_prompt' and selected:
            wires.append(row)
    if not selected: parser.error('requested final_prompt not present in this log')
    if args.attempt:
        match = next((w for w in wires if w['attempt']==args.attempt), None)
        if match is None: parser.error('wire attempt not present (mock/custom transports may not support wire audit)')
        result = match['request_body']
    else:
        result = dict(messages=selected['messages'], memory_ids=selected['memory_ids'],
                      wire_attempts_available=[w['attempt'] for w in wires])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
