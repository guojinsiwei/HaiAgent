"""Zero-model Docker isolation probe; uses an already downloaded selected image."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE / 'bestfgs-project/src'), str(HERE / 'hai-project/src')]
from docker_state import DockerState, PYTHON, LABEL

def main():
    name = 'lhtb-zero-probe-' + uuid.uuid4().hex[:12]
    image = 'zli12321/lhtb-matpower-opf-regression:20260615'
    def docker(*args):
        return subprocess.check_output(['docker', *map(str, args)], text=True).strip()
    original = docker('run', '-d', '--name', name, '--label', LABEL + '=' + name,
        '--network', 'none', '--cpus', '2', '--memory', '4g', '--entrypoint', '/bin/sh',
        image, '-c', 'sleep 3600')
    state = None
    try:
        docker('exec', original, 'mkdir', '-p', '/opt/lhtb-agent-tools', '/app')
        docker('cp', '/mnt/sdb/home/lizh639/terminalbench-v14-setup/python/cpython-3.12.12-linux-x86_64-gnu', original + ':/opt/lhtb-agent-tools/python')
        docker('cp', str(HERE / 'hai-project/src'), original + ':/opt/lhtb-agent-tools/src')
        docker('cp', str(HERE / 'container_command.py'), original + ':/opt/lhtb-agent-tools/container_command.py')
        state = DockerState(original, HERE / name, 2, 4096, time.monotonic() + 600)
        child = state.branch(state.initial)
        result = state.command(child, {'argv': [PYTHON, '-c', "from pathlib import Path; Path('/app/probe.txt').write_text('child'); Path('/tmp/probe-outside').write_text('outside')"],
                                      'cwd': '/app', 'stdin': None, 'timeout_seconds': 30})
        if result.exit_code != 0:
            raise RuntimeError('Fixture command failed')
        changed = state.capture(child, state.initial)
        state.remove(child)
        sibling = state.branch(state.initial)
        result = state.command(sibling, {'argv': [PYTHON, '-c', "from pathlib import Path; assert not Path('/app/probe.txt').exists(); assert not Path('/tmp/probe-outside').exists(); print('sibling isolated')"],
                                        'cwd': '/app', 'stdin': None, 'timeout_seconds': 30})
        if result.exit_code != 0:
            raise RuntimeError('Sibling isolation failed')
        state.remove(sibling)
        resumed = state.branch(changed)
        result = state.command(resumed, {'argv': [PYTHON, '-c', "from pathlib import Path; assert Path('/app/probe.txt').read_text()=='child'; assert Path('/tmp/probe-outside').read_text()=='outside'; print('full rootfs restored')"],
                                        'cwd': '/app', 'stdin': None, 'timeout_seconds': 30})
        if result.exit_code != 0:
            raise RuntimeError('Snapshot restoration failed')
        state.remove(resumed)
        state.deliver(changed)
        actual = docker('exec', original, 'cat', '/app/probe.txt')
        if actual != 'child':
            raise RuntimeError('Delivery mismatch')
        result = {'passed': True, 'model_calls': 0, 'checks': ['sibling_app_isolation',
            'sibling_rootfs_isolation', 'full_rootfs_restore', 'selected_artifact_delivery'],
            'state_dir': str(state.root)}
        (HERE / 'docker-probe.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    finally:
        if state:
            for container in list(state.containers):
                state.remove(container)
        info = json.loads(docker('inspect', original))[0]
        if info['Config']['Labels'].get(LABEL) != name:
            raise RuntimeError('Probe cleanup ownership mismatch')
        docker('rm', '-f', original)

if __name__ == '__main__':
    main()
