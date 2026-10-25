"""Test-only Harbor agent. Not referenced by any formal job configuration."""
from pathlib import Path
import shlex
import json
import tempfile
from cloud_agent import CloudAgent, TLS_ENV, common_args

class ScriptedFixtureAgent(CloudAgent):
    async def run(self,instruction,environment,context):
        probe = "import urllib.request, urllib.error\ntry:\n urllib.request.urlopen('https://api.deepseek.com/models',timeout=25)\nexcept urllib.error.HTTPError as error:\n assert error.code == 401, error.code\n print('UNAUTHENTICATED_API_ROUTE_OK')\n"
        route = await environment.exec('/installed-agent/python/bin/python3.12 -c '+shlex.quote(probe),user='root',env=TLS_ENV,timeout_sec=35)
        if route.return_code or 'UNAUTHENTICATED_API_ROUTE_OK' not in route.stdout:
            raise RuntimeError('Official restricted-network API route check failed; no key was sent: '+str(route.return_code)+' '+str(route.stdout)[-1800:]+' '+str(route.stderr)[-200:])
        await environment.upload_file(Path(__file__).with_name('fixture_runner.py'),'/installed-agent/fixture_runner.py')
        with tempfile.TemporaryDirectory() as directory:
            payload=Path(directory)/'input.json'
            payload.write_text(json.dumps({'method':self.method,'args':common_args('deepseek-flash',self.method),
                                           'instruction':instruction,'timeout':100}))
            await environment.upload_file(payload,'/installed-agent/input.json')
        result=await environment.exec('/installed-agent/python/bin/python3.12 /installed-agent/fixture_runner.py',env={**TLS_ENV,'DEEPSEEK_API_KEY':'fixture-unused'},user='root',timeout_sec=130)
        if result.return_code:
            raise RuntimeError('Loopback CLI fixture failed: '+str(result.stdout)[-1200:])
