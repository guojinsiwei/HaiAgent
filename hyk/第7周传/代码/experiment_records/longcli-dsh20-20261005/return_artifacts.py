"""Package only public results/logs; exclude credentials and the DSH home."""
import json
from pathlib import Path
import tarfile
import time

from common import ROOT


def main():
    health = json.loads((ROOT / 'health.json').read_text())
    assert health['state'] in ('complete', 'needs_attention')
    target = ROOT / ('results-' + str(int(time.time())) + '.tar.gz')
    paths = [ROOT / name for name in ('protocol.json', 'installation.json', 'deployment-manifest.json',
                                    'environment-acceptance.json', 'keyless-acceptance.json', 'health.json', 'summary.json')]
    for job in sorted((ROOT / 'jobs').iterdir()):
        if not job.is_dir() or job.is_symlink():
            continue
        paths += [job / name for name in ('summary.json', 'health.json', 'isolation.json', 'console.jsonl',
                                         'stderr.log', 'audit/events.jsonl')]
    for path in (ROOT / 'grades').glob('*/result.json'):
        paths.append(path)
        paths += list((path.parent / 'test_output').glob('*.json'))
        paths += list((path.parent / 'test_output').glob('*.txt'))
        paths.append(path.parent / 'console.log')
    with tarfile.open(target, 'x:gz') as stream:
        for path in paths:
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT.resolve()):
                stream.add(path, arcname=path.relative_to(ROOT).as_posix(), recursive=False)
    print(json.dumps({'state': health['state'], 'archive': str(target),
                      'generation_done': len(health['generation_done']), 'graded': len(health['grading_done'])}))


if __name__ == '__main__':
    main()
