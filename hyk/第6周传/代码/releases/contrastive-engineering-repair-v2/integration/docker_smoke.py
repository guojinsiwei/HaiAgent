"""Actual isolated Docker timeout -> next action -> snapshot -> delivery. No API."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'integration'),str(ROOT/'sources/bestfgs-project/src'),
               str(ROOT/'sources/hai-project/src')]
from docker_state import DockerState, LABEL, PYTHON

IMAGE = 'sha256:4e80a104af85cccd260ada0b737513aae8722acd4bea22f9f3002ba7b9c222d4'
RUNTIME = Path('/mnt/sdb/home/lizh639/terminalbench-v14-setup/python/cpython-3.12.12-linux-x86_64-gnu')


def docker(*args):
    result = subprocess.run(['docker',*map(str,args)],capture_output=True,text=True,timeout=120)
    if result.returncode:
        raise RuntimeError('Smoke Docker failure: '+args[0])
    return result.stdout.strip()


def main():
    state = None
    original = None
    owner = uuid.uuid4().hex
    try:
        docker('image','inspect',IMAGE)  # cached exact image; never pull
        original = docker('run','-d','--init','--network','none','--cpus','1',
            '--memory','512m','--pids-limit','128','--label',LABEL+'='+owner,
            '--entrypoint','/bin/sh',IMAGE,'-c','sleep 600')
        docker('exec',original,'mkdir','-p','/app','/opt/lhtb-agent-tools')
        docker('cp',RUNTIME,original+':/opt/lhtb-agent-tools/python')
        docker('cp',ROOT/'sources/hai-project/src',original+':/opt/lhtb-agent-tools/src')
        for name in ('container_command.py','process_cleanup.py'):
            docker('cp',ROOT/'integration'/name,original+':/opt/lhtb-agent-tools/'+name)
        docker('cp',ROOT/'sources/bestfgs-project/src/bestfgs/shell_probe.py',
               original+':/opt/lhtb-agent-tools/shell_probe.py')
        os.environ['LHTB_DISABLE_DISK_GUARD'] = '1'
        state = DockerState(original, ROOT/('docker-smoke-'+owner), 1, 512, time.monotonic()+300)
        branch = state.branch(state.initial)
        first = state.command(branch,dict(argv=['bash','-lc','timeout 30 sleep 60 | tail -1'],
            cwd='.',timeout_seconds=.3,capture_execution=True))
        assert first.timed_out and first.execution_observation['process_cleanup']['complete']
        assert first.execution_observation['process_cleanup']['killed'] >= 1
        detached = state.command(branch,dict(argv=[PYTHON,'-c',
            'import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"],start_new_session=True)'],
            cwd='.',timeout_seconds=10,capture_execution=True))
        assert detached.exit_code == 126
        assert detached.execution_observation['process_cleanup']['file_only_violation']
        assert detached.execution_observation['process_cleanup']['command_exit_code'] == 0
        import hashlib
        # Hashes describe captured raw stream bytes, not the display rendering.
        # An inherited pipe may still be open at capture time; the executor then
        # inserts an omission marker without hashing that synthetic marker.
        assert detached.stderr_bytes == 0
        assert detached.stderr_sha256 == hashlib.sha256(b'').hexdigest()
        assert detached.stderr in ('', '\n[output omitted]\n')
        if detached.stderr:
            assert detached.output_truncated and detached.background_output_open
        second = state.command(branch,dict(argv=[PYTHON,'-c',
            'from pathlib import Path; Path("engineering-smoke-marker.txt").write_text("recovered"); print("NEXT_ACTION_OK")'],
            cwd='.',timeout_seconds=10,capture_execution=True))
        assert second.exit_code == 0 and 'NEXT_ACTION_OK' in second.stdout
        snap = state.capture(branch,state.initial)
        state.deliver(snap)
        delivered = docker('exec',original,PYTHON,'-c',
            'from pathlib import Path; assert Path("/app/engineering-smoke-marker.txt").read_text()=="recovered"; print("DELIVERY_OK")')
        assert delivered == 'DELIVERY_OK'
        print(json.dumps(dict(test='real_docker_timeout_snapshot_delivery',passed=True,
            descendant_cleanup=first.execution_observation['process_cleanup'],
            detached_launcher_exit=detached.exit_code,raw_stderr_hash_preserved=True,
            followup_exit=second.exit_code,delivery='DELIVERY_OK',model_api_calls=0)))
    finally:
        if state is not None:
            for container in list(state.containers):
                state.remove(container)  # exact owned IDs and label checks
            for image in list(state.images):
                info = json.loads(docker('image','inspect',image))[0]
                if (info['Config'].get('Labels') or {}).get(LABEL) != state.owner:
                    raise RuntimeError('Refuse cleanup of unowned smoke image')
                docker('image','rm',image)
        if original is not None:
            info = json.loads(docker('inspect',original))[0]
            if (info['Config'].get('Labels') or {}).get(LABEL) != owner:
                raise RuntimeError('Refuse cleanup of unowned smoke container')
            docker('rm','-f',original)


if __name__ == '__main__': main()
