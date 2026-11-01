"""One immutable artifact, one grader launch; never automatically regrade."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from common import ROOT, save, sha


def grade_job(job):
    assert job in {'dsh--' + r['task'] for r in json.loads((ROOT / 'protocol.json').read_text())['tasks']}
    directory = ROOT / 'incoming' / job
    summary = json.loads((directory / 'summary.json').read_text())
    archive = directory / 'final-source.tar.gz'
    assert summary['artifact']['sha256'] == sha(archive)
    os.close(os.open(directory / 'grading.claim', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    from college_grader import grade, docker
    result = grade(job, archive, summary['artifact']['sha256'])
    container = result['container']
    assert docker('inspect', container, '--format', '{{index .Config.Labels "experiment"}}').stdout.strip() == 'longcli-dsh20-matched-20261005'
    assert docker('inspect', container, '--format', '{{.State.Running}}').stdout.strip() == 'false'
    docker('rm', container)
    result['grading_container_destroyed'] = True
    save(ROOT / 'grades' / job / 'result.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--start', action='store_true')
    args = parser.parse_args()
    assert args.job in {'dsh--' + r['task'] for r in json.loads((ROOT / 'protocol.json').read_text())['tasks']}
    if (ROOT / 'grades' / args.job / 'result.json').exists():
        print((ROOT / 'grades' / args.job / 'result.json').read_text())
    elif (ROOT / 'incoming' / args.job / 'grading.claim').exists():
        print(json.dumps({'state': 'grading_already_claimed', 'job': args.job}))
    elif args.start:
        directory = ROOT / 'incoming' / args.job
        claim = directory / 'grading-launch.claim'
        try:
            os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
        except FileExistsError:
            print(json.dumps({'state': 'grading_launch_already_claimed', 'job': args.job}))
            raise SystemExit(0)
        with (directory / 'grading-worker.log').open('x') as output, (directory / 'grading-stderr.log').open('x') as error:
            process = subprocess.Popen([sys.executable, '-B', str(ROOT / 'grade_one.py'), '--job', args.job],
                                       stdout=output, stderr=error, stdin=subprocess.DEVNULL, start_new_session=True)
        save(directory / 'grading-launch.json', {'pid': process.pid, 'job': args.job})
        print(json.dumps({'state': 'grading_started', 'job': args.job}))
    else:
        grade_job(args.job)
