"""Shared command and credential plumbing for the real gate and real task."""
import json
import os
from pathlib import Path
import signal
import subprocess

def execute(key, prompt, workspace, logs, config, request_limit, timeout):
    logs=Path(logs)
    logs.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ)
    # Isolate from ambient vendor keys/settings; only this trial's key is admitted.
    for name in ('DEEPSEEK_API_KEY','DEEPSEEK_BASE_URL','ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL'):
        env.pop(name,None)
    env.update(TAOTOKEN_API_KEY=key, DSH_HOME=str(logs/'dsh-home'),
        KZ_WORKSPACE=workspace,KZ_AUDIT_DIR=str(logs/'kz-audit'),
        DSH_PERMISSION_MODE='danger-full-access', HTTPS_PROXY='http://10.123.0.1:28476',
        NO_PROXY='127.0.0.1,localhost',PATH='/opt/node/bin:'+env.get('PATH',''),
        DSH_ROUTE_AUDIT=str(logs/'request-route.jsonl'),DSH_WIRE_REQUEST_LIMIT=str(request_limit),
        DSH_EXPECT_ENDPOINT='https://api.taotoken.net/token/v1/messages')
    command=['/opt/node/bin/node','--use-env-proxy','--import','/opt/kz/route-audit.mjs',
        '/opt/kz/node_modules/@deepseek-ai/dsh/lib/bin.js','--profile','headless',
        '--patch','/opt/kz/config/common.patch.yml','--patch','/opt/kz/route.patch.yml',
        '--patch',config,'--json','-']
    with (logs/'dsh.jsonl').open('wb') as out,(logs/'dsh.stderr.log').open('wb') as err:
        process=subprocess.Popen(command,cwd=workspace,env=env,stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True)
        try:
            process.communicate(prompt.encode(),timeout=timeout)
            code=process.returncode
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait()
            code=124
    (logs/'agent-exit.json').write_text(json.dumps({'exit_code':code}))
    return code

def json_lines(path):
    if not Path(path).exists(): return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
