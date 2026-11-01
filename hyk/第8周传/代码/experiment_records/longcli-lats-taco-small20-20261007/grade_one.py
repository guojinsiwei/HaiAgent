"""One immutable artifact, one grader launch; never automatically regrade."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from common import ROOT, save, sha


def valid_jobs():
    protocol=json.loads((ROOT/'protocol.json').read_text())
    return {method+'--'+row['task'] for method in protocol['methods'] for row in protocol['tasks']}


def grade_job(job):
    import fcntl
    import time
    # Serialize only our graders, without inspecting unrelated users' containers.
    with Path('/var/tmp/lizh639-longcli-owned-grader.lock').open('a') as lock:
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except BlockingIOError:
                save(ROOT/'grading-health.json',{'state':'waiting_for_owned_grader',
                     'job':job,'updated':time.time(),'model_calls':0})
                time.sleep(5)
        return _grade_job(job)


def _grade_job(job):
    assert job in valid_jobs()
    directory = ROOT / 'incoming' / job
    summary = json.loads((directory / 'summary.json').read_text())
    archive = directory / 'final-source.tar.gz'
    assert summary['artifact']['sha256'] == sha(archive)
    os.close(os.open(directory / 'grading.claim', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    import college_grader as grader
    from grading_adapter import install
    from grading_adapter import cleanup_docker as docker
    cleanup=install(grader)
    # This process only grades one immutable artifact; no model request is made.
    result=None
    experiment = json.loads((ROOT / 'protocol.json').read_text())['experiment']
    try:
        result = grader.grade(job, archive, summary['artifact']['sha256'])
    except Exception as error:
        result={'job':job,'grading_state':'failed','official_success':None,
                'error_type':type(error).__name__,'artifact_sha256':summary['artifact']['sha256']}
    finally:
        # Durable result even when docker run failed before the official try/finally.
        if result is not None:save(ROOT/'grades'/job/'result.json',result)
        removed=[]
        for container in cleanup['owned']:
            try:
                observed=docker('inspect',container,'--format','{{json .Config.Labels}}',check=False,seconds=8)
                if observed.returncode and 'no such' in observed.stderr.lower():
                    removed.append(container);continue
                assert observed.returncode==0 and json.loads(observed.stdout).get('experiment')==experiment
                if docker('inspect',container,'--format','{{.State.Running}}',seconds=8).stdout.strip()=='true':
                    docker('kill',container,check=False,seconds=10)
                assert docker('inspect',container,'--format','{{.State.Running}}',seconds=8).stdout.strip()=='false'
                docker('rm',container,seconds=10);removed.append(container)
            except Exception as error:
                cleanup['errors'].append({'container':container,'error':type(error).__name__})
        if result is not None:
            result['grading_container_destroyed']=len(removed)==len(cleanup['owned'])
            if cleanup['errors']:result['grading_cleanup_errors']=cleanup['errors']
            save(ROOT/'grades'/job/'result.json',result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    parser.add_argument('--start', action='store_true')
    args = parser.parse_args()
    assert args.job in valid_jobs()
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
