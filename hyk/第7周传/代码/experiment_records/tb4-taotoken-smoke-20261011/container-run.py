"""Receive credential on an anonymous pipe; never put it in argv or a file."""
import json
import os
from pathlib import Path
import subprocess
import sys

key = sys.stdin.buffer.readline(8192).decode().strip()
if not key or len(key) > 8000:
    raise SystemExit('Missing or malformed credential input')
env = dict(os.environ)
env.update(TAOTOKEN_API_KEY=key, DSH_HOME='/logs/agent/dsh-home',
           KZ_WORKSPACE='/app', KZ_AUDIT_DIR='/logs/agent/kz-audit',
           DSH_PERMISSION_MODE='danger-full-access',
           HTTPS_PROXY='http://10.123.0.1:28476', NO_PROXY='127.0.0.1,localhost',
           PATH='/opt/node/bin:' + env.get('PATH', ''))
command = ['/opt/node/bin/node', '--use-env-proxy', '/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js',
           'headless', '--patch', '/opt/kz/config/common.patch.yml',
           '--patch', '/opt/kz/route.patch.yml',
           '--patch', '/opt/kz/.runtime/kz.patch.yml', '--json', '-']
Path('/logs/agent').mkdir(parents=True, exist_ok=True)
with open('/logs/agent/dsh.jsonl', 'wb') as out, open('/logs/agent/dsh.stderr.log', 'wb') as err:
    process = subprocess.Popen(command, cwd='/app', env=env, stdin=subprocess.PIPE,
                               stdout=out, stderr=err, start_new_session=True)
    try:
        process.communicate(Path('/opt/kz/instruction.txt').read_bytes(), timeout=1900)
        code = process.returncode
    except subprocess.TimeoutExpired:
        import signal
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        code = 124
Path('/logs/agent/agent-exit.json').write_text(json.dumps({'exit_code': code}))
print(json.dumps({'agent_exit_code': code, 'logs': '/logs/agent/'}))
raise SystemExit(code)
