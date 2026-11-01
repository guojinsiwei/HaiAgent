"""Synchronize candidate metadata before paid trials; never change grading."""
import json
from common import ROOT, save

old = json.loads((ROOT / 'protocol.json').read_text())
new = json.loads((ROOT / 'generation-protocol.json').read_text())
assert not any((ROOT / 'incoming').iterdir()), 'Generation already delivered; preserve frozen grading protocol'
for key in ('experiment', 'commit', 'tasks', 'grading_resources', 'methods', 'total_trials',
            'model', 'thinking', 'temperature', 'max_turns', 'max_tools', 'max_tokens', 'input_bytes'):
    assert old[key] == new[key], 'Refusing to change grading, cohort or budgets: ' + key
new['grading_directory'] = str(ROOT)
if old != new:
    archive = ROOT / 'protocol-pre-final-acceptance.json'
    assert not archive.exists(), 'Metadata sync already occurred; do not overwrite archive'
    save(archive, old)
    save(ROOT / 'protocol.json', new)
print(json.dumps({'state': 'grading_metadata_synchronized', 'grading_changed': False, 'paid_api_requests': 0}))
