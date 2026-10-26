"""Remove a stale per-step truncation after the existing controller resumes."""
from pathlib import Path
import hashlib
import json

TARGET = Path('/opt/kz/node_modules/@deepseek-ai/dsh-agent-loop/lib/index.js')
OLD = 'if (turnEnds === null || turnEnds.kind !== "max-tokens") turnEnds = stepEnd;'
NEW = 'turnEnds = stepEnd; // A resumed step replaces the previous step stop reason.'


def patch(path=TARGET):
    source = path.read_text()
    if source.count(OLD) != 1:
        raise RuntimeError('Unexpected DSH loop version; refusing patch')
    backup = path.with_name(path.name + '.before-max-tokens')
    with backup.open('x') as f:
        f.write(source)
    fixed = source.replace(OLD, NEW)
    path.write_text(fixed)
    receipt = dict(file=str(path), before=hashlib.sha256(source.encode()).hexdigest(),
                   after=hashlib.sha256(fixed.encode()).hexdigest(), replacements=1,
                   token_limits_unchanged=True)
    Path('/logs/agent/max-tokens-patch.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt))


if __name__ == '__main__':
    patch()
