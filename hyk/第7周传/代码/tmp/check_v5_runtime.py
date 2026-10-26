import hashlib
import json
import os
from pathlib import Path
import re
import time

root = Path('/mnt/lizh639/bestfgs-runs/swe100-paired-v3')
expected = '7a01769a47fe0ab75a5edf830e05d1b3b6905df6baba3a9383f3189d9ea8d2e1'
index = {'lizh639-aa91': 0, 'lizh639-8e64': 1}[os.uname().nodename]
protocol = json.loads((root / 'comparison-protocol.json').read_text())
sha = hashlib.sha256(json.dumps(protocol, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
assert sha == expected
ids = protocol['sharding']['workers'][index]
processes = []
for p in Path('/proc').iterdir():
    if p.name.isdigit():
        try:
            argv = (p / 'cmdline').read_bytes().decode(errors='replace').split('\0')
            if argv and 'python' in Path(argv[0]).name:
                if any(a.endswith('/run_comparison.py') or a.endswith('/paired_health_guard_v5.py') for a in argv):
                    processes.append({'pid': int(p.name), 'scripts': [a for a in argv if a.endswith('.py')]})
        except OSError:
            pass
states = []
for method in ('bestfgs', 'raw'):
    for identity in ids:
        file = root / method / 'states' / (identity + '.json')
        if not file.is_file():
            continue
        state = json.loads(file.read_text())
        child = root / method / 'search' / identity / identity / 'status.json'
        if child.is_file():
            attempt = Path(json.loads(child.read_text())['attempt'])
            log = attempt / 'agent.log'
            text = log.read_text(errors='replace') if log.is_file() else ''
            lines = text.splitlines()
            safe_tail = [re.sub(r'(?i)sk-[a-z0-9_-]+', '[REDACTED]', line) for line in lines[-5:]]
        else:
            log = Path('/nonexistent')
            text, safe_tail = '', []
        states.append({'method': method, 'id': identity, 'status': state['status'],
                       'attempt_count': state.get('attempt_count'), 'stop_reason': state.get('stop_reason'),
                       'log_age': round(time.time() - log.stat().st_mtime) if log.exists() else None,
                       'parsed_responses': text.count('模型响应已收到并解析为JSON'),
                       'tool_batches': text.count('CLI执行结束'), 'tail': safe_tail})
health = root / 'health' / f'worker-{index}.json'
print(json.dumps({'host': os.uname().nodename, 'protocol_ok': True, 'processes': processes,
                  'health': json.loads(health.read_text()) if health.exists() else None, 'states': states}, ensure_ascii=False))
