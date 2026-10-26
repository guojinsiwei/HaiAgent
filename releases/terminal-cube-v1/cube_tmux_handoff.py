"""Resume the same pilot in tmux after a graceful foreground shutdown."""
import argparse
from contextlib import redirect_stdout
import getpass
import io
import json
import os
from pathlib import Path
import signal
import sys
import time

import run_notebook
import run_terminal_bench_cube as cube
from benchmark_runtime import atomic_write_json, canonical_sha256, implementation_sha256


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', required=True, type=Path)
    parser.add_argument('--old-pid', required=True, type=int)
    args = parser.parse_args()
    root = args.output_root.resolve()
    protocol = json.loads((root / 'pilot-protocol.json').read_text())
    if protocol['implementation_sha256'] != implementation_sha256(cube.ROOT):
        raise ValueError('Original implementation changed; refusing to mix runs')
    if cube.sha(root / 'tasks.json') != protocol['task_manifest_sha256']:
        raise ValueError('Original task manifest changed')
    os.environ.update(PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH']

    def command(method):
        return ['--task-manifest', str(root / 'tasks.json'), '--output-root', str(root / method),
                '--method', method, '--task-timeout', str(protocol['task_timeout_seconds'])]

    # Validate reuse before interrupting anything. No model calls in dry-run.
    for method in cube.METHODS:
        saved = root / method / 'notebook-run.json'
        if saved.exists():
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = run_notebook.main(command(method) + ['--dry-run', '--', *protocol['agent_args']])
            if code or canonical_sha256(json.loads(buffer.getvalue())) != json.loads(saved.read_text())['fingerprint']:
                raise ValueError('Resume fingerprint mismatch; foreground run left untouched')
    print('Ready to move this two-task pilot into tmux. Original results will be retained.', flush=True)
    key = getpass.getpass('DeepSeek API Key (hidden): ').strip()
    if not key or any(c.isspace() for c in key):
        raise ValueError('Empty/invalid key; foreground run left untouched')
    os.environ['DEEPSEEK_API_KEY'] = key
    del key
    process = Path('/proc') / str(args.old_pid)
    if process.exists():
        argv = (process / 'cmdline').read_bytes().split(b'\0')
        if b'run_terminal_bench_cube.py' not in argv or str(root).encode() not in argv:
            raise ValueError('Old PID no longer identifies the expected pilot; nothing stopped')
        print('Stopping the old foreground runner gracefully...', flush=True)
        os.kill(args.old_pid, signal.SIGTERM)
        deadline = time.monotonic() + 45
        while process.exists() and time.monotonic() < deadline:
            time.sleep(0.25)
        if process.exists():
            raise RuntimeError('Old runner did not exit; refusing to start a duplicate')
    atomic_write_json(root / 'tmux-handoff.json', {'old_pid': args.old_pid, 'new_pid': os.getpid(),
                                                'time_unix': time.time(), 'mode': 'resume_completed_restart_interrupted',
                                                'tmux_session': 'terminal-cube-pilot', 'tmux_socket': 'terminal-cube-v1'})
    print('TMUX RUNNING: you may close SSH or shut down your computer now.', flush=True)
    codes = []
    for method in cube.METHODS:
        flags = ['--resume'] if (root / method / 'notebook-run.json').exists() else []
        codes.append(run_notebook.main(command(method) + flags + ['--', *protocol['agent_args']], expected_benchmark='terminal-bench'))
        cube.report(root, verify=True)
        if codes[-1] == 130:
            return 130
    print(json.dumps(cube.report(root), indent=2), flush=True)
    return 2 if any(codes) else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Handoff stopped: {exc}', file=sys.stderr, flush=True)
        raise SystemExit(2)
