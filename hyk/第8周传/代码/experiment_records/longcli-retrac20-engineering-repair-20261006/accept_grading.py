"""Score only a pristine starter to verify official artifact transport/grading."""
import json
from pathlib import Path
from common import ROOT, save, sha
from college_grader import grade, docker

archive = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004/starter-cs61_fa24_cats.tar.gz')
existing = ROOT / 'fixture-grades/roundtrip--cs61_fa24_cats/result.json'
experiment = json.loads((ROOT / 'protocol.json').read_text())['experiment']
if existing.exists():
    result = json.loads(existing.read_text())
    assert result['fixture'] and result['artifact_sha256'] == sha(archive)
else:
    result = grade('roundtrip--cs61_fa24_cats', archive, sha(archive), fixture=True)
container = result['container']
if docker('ps', '-a', '--filter', 'name=^/' + container + '$', '--format', '{{.Names}}').stdout.strip():
    assert docker('inspect', container, '--format', '{{index .Config.Labels "experiment"}}').stdout.strip() == experiment
    assert docker('inspect', container, '--format', '{{.State.Running}}').stdout.strip() == 'false'
    docker('rm', container)
assert result['grading_state'] == 'complete'
assert result['p2p_count'] == 19 and sum(result['p2p_cases'].values()) == 18
assert result['p2p_step_score'] == 0.947  # Official parser rounds to three significant digits.
assert any('READMD.md' in name and passed == 0 for name, passed in result['p2p_cases'].items())
save(ROOT / 'grading-acceptance.json', {'state': 'passed', 'paid_api_requests': 0, 'pristine_starter': True,
                                      'known_upstream_defect_preserved': True, 'result': result})
print(json.dumps({'state': 'grading_acceptance_passed', 'paid_api_requests': 0}))
