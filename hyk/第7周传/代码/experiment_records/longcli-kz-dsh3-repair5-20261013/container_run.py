"""Receive a key once via anonymous stdin, never command arguments or disk."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

bundle=json.loads(sys.stdin.readline(16384))
key=bundle.pop('key')
assert key and not any(c.isspace() for c in key)
logs=Path('/audit')
env=dict(os.environ)
for name in ('DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL'):
    env.pop(name,None)
env.update(TAOTOKEN_API_KEY=key,DSH_HOME='/dsh-home',KZ_WORKSPACE='/app',KZ_AUDIT_DIR='/audit/kz',
    DSH_PERMISSION_MODE='danger-full-access',DSH_APPROVAL_POLICY='never',DSH_TELEMETRY_DISABLED='1',
    HTTPS_PROXY=bundle['proxy'],NO_PROXY='localhost,127.0.0.1',
    PATH='/opt/node/bin:'+env.get('PATH',''),DSH_ROUTE_AUDIT='/audit/request-route.jsonl',
    DSH_WIRE_REQUEST_LIMIT='800',DSH_EXPECT_ENDPOINT='https://api.taotoken.net/token/v1/messages')
command=['/opt/node/bin/node','--use-env-proxy','--import','/opt/kz/route-audit.mjs',
    '--import','/opt/kz/kz-boot-guard.mjs',
    '/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js','--profile','headless']
for patch in ('config/common.patch.yml','route.patch.yml','.runtime/kz.patch.yml'):
    command += ['--patch','/opt/kz/'+patch]
command += ['--json','-']
prompt=Path('/opt/experiment/instruction.txt').read_bytes()
with (logs/'dsh.jsonl').open('xb') as out,(logs/'dsh.stderr.log').open('xb') as err:
    p=subprocess.Popen(command,cwd='/app',env=env,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True)
    key='';env.pop('TAOTOKEN_API_KEY',None)
    try:
        p.communicate(prompt,timeout=7200)
        code=p.returncode
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);p.wait()
        code=124
(logs/'agent-exit.json').write_text(json.dumps({'exit_code':code}))
sys.exit(code)
