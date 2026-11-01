"""Reuse the unchanged pinned official grader; never run paid generation here."""
import json
from pathlib import Path
import shutil
from common import ROOT, save, sha

PREVIOUS = Path('/var/tmp/lizh639-longcli-dsh20-repair2-20261005')
BASE = Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')


def main():
    assert not (ROOT / 'protocol.json').exists()
    previous = json.loads((BASE / 'protocol.json').read_text())
    protocol = json.loads((ROOT / 'generation-protocol.json').read_text())
    assert protocol['methods'] == ['dsh'] and protocol['total_trials'] == 20
    assert protocol['tasks'] == previous['tasks'] and protocol['commit'] == previous['commit']
    assert protocol['grading_resources'] == previous['grading_resources']
    protocol['grading_directory'] = str(ROOT)
    save(ROOT / 'protocol.json', protocol)
    for filename in ('college_grader.py', 'input-manifest.json'):
        shutil.copyfile(PREVIOUS / filename, ROOT / filename)
    (ROOT / 'upstream').symlink_to((PREVIOUS / 'upstream').resolve(), target_is_directory=True)
    (ROOT / 'incoming').mkdir()
    save(ROOT / 'grading-ready.json', {'ready': True, 'paid_api_requests': 0, 'grader_sha256': sha(ROOT / 'college_grader.py'),
                                       'historical_grader_sha256': sha(PREVIOUS / 'college_grader.py')})
    print(json.dumps({'state': 'grading_ready', 'tasks': 20, 'paid_api_requests': 0}))


if __name__ == '__main__':
    main()
