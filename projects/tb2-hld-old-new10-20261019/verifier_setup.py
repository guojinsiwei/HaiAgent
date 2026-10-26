"""Stage attested offline dependency caches after solving; keep official tests intact."""
import contextlib,hashlib,importlib.util,json,shlex,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class VerifierInfrastructureError(RuntimeError):pass
@contextlib.contextmanager
def verifier_network(verifier):
 spec=importlib.util.spec_from_file_location('verifier_egress_proxy',ROOT/'dependencies/network_proxy.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 server=module.ThreadingHTTPServer((module.HOST,0),module.Handler)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 proxy='http://%s:%d'%server.server_address;old=dict(verifier.verifier_env or {})
 verifier.verifier_env=dict(old,HTTP_PROXY=proxy,HTTPS_PROXY=proxy,http_proxy=proxy,https_proxy=proxy,NO_PROXY='localhost,127.0.0.1,::1',no_proxy='localhost,127.0.0.1,::1')
 try:yield
 finally:server.shutdown();server.server_close();worker.join(timeout=5);verifier.verifier_env=old
def validate_test_report(verifier):
 path=verifier.trial_paths.verifier_dir/'ctrf.json'
 if not path.is_file():raise VerifierInfrastructureError('Official test report missing; inspect test-stdout.txt. No score accepted.')
 try:report=json.loads(path.read_text())
 except ValueError as e:raise VerifierInfrastructureError('Malformed official test report') from e
 result=report.get('results',{});summary=result.get('summary',{});tests=result.get('tests',[])
 if type(summary.get('tests')) is not int or summary['tests']<=0 or len(tests)!=summary['tests']:
  raise VerifierInfrastructureError('Official tests did not execute completely; no score accepted')
 if any(t.get('status') not in ('passed','failed','skipped','pending','other') for t in tests):raise VerifierInfrastructureError('Unknown test result status')
 reward=verifier.trial_paths.verifier_dir/'reward.txt'
 if reward.exists() and reward.read_text().strip()=='1' and any(t.get('status')=='failed' for t in tests):raise VerifierInfrastructureError('Reward contradicts official test report')
async def prepare_verifier(verifier):
 name=verifier.task.paths.task_dir.name;folder=ROOT/'dependency-cache'/name
 spec=json.loads((folder/'ready.json').read_text());archive=folder/'dependencies.tar'
 if hashlib.sha256((verifier.task.paths.task_dir/'tests/test.sh').read_bytes()).hexdigest()!=spec['test_sha256']:raise VerifierInfrastructureError('Official test script changed')
 with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
 if archive.is_symlink() or digest!=spec['archive_sha256']:raise VerifierInfrastructureError('Dependency archive drift')
 env=verifier.environment;target='/tmp/kz-score-deps.tar'
 await env.upload_file(archive,target)
 command=f"""set -eu
test ! -L {target}
test ! -L /opt/kz-verifier
printf '%s  %s\\n' {shlex.quote(digest)} {target} | sha256sum -c -
tar -xf {target} -C /opt
rm {target}
mkdir -p /opt/kz-verifier/shims "$HOME/.local/bin"
cp /opt/kz-verifier/bin/uv /opt/kz-verifier/bin/uvx "$HOME/.local/bin/"
cat > "$HOME/.local/bin/env" <<'EOF'
export PATH="/opt/kz-verifier/shims:$HOME/.local/bin:$PATH"
EOF
cat > /opt/kz-verifier/offline-install.sh <<'EOF'
#!/bin/sh
set -eu
mkdir -p "$HOME/.local/bin"
cp /opt/kz-verifier/bin/uv /opt/kz-verifier/bin/uvx "$HOME/.local/bin/"
EOF
cat > /opt/kz-verifier/shims/curl <<'EOF'
#!/bin/sh
for arg in "$@"; do
 if [ "$arg" = 'https://astral.sh/uv/0.9.5/install.sh' ]; then cat /opt/kz-verifier/offline-install.sh; exit 0; fi
done
exec /usr/bin/curl --retry 3 --retry-all-errors --connect-timeout 30 "$@"
EOF
chmod 755 /opt/kz-verifier/shims/curl
"""
 result=await env.exec(command=command,user='root',timeout_sec=900)
 (verifier.trial_paths.verifier_dir/'dependency-bootstrap.log').write_text((result.stdout or '')+'\n'+(result.stderr or ''))
 if result.return_code:raise VerifierInfrastructureError('Offline dependency staging failed')
 verifier.verifier_env=dict(verifier.verifier_env or {},PATH='/opt/kz-verifier/shims:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',UV_CACHE_DIR='/opt/kz-verifier/cache',UV_PYTHON_INSTALL_DIR='/opt/kz-verifier/python',UV_OFFLINE='true',UV_PYTHON_DOWNLOADS='never',UV_INDEX_URL='https://pypi.org/simple',UV_LINK_MODE='copy',PIP_NO_INDEX='1',PIP_FIND_LINKS='/opt/kz-verifier/wheels',PIP_DISABLE_PIP_VERSION_CHECK='1')
 # Prove the same dependency resolution works with networking disabled before
 # entering Harbor's original verifier timeout. Test assertions remain untouched.
 if spec['kind']=='uv':
  cmd='/opt/kz-verifier/bin/uvx --offline '+shlex.join(spec['args'][1:])
 else:cmd='python -m pip install --no-index --find-links=/opt/kz-verifier/wheels '+shlex.join(spec['args'][6:])+' --break-system-packages'
 result=await env.exec(command=cmd,user='root',env=verifier.verifier_env,timeout_sec=600)
 (verifier.trial_paths.verifier_dir/'offline-resolution.log').write_text((result.stdout or '')+'\n'+(result.stderr or ''))
 if result.return_code:raise VerifierInfrastructureError('Offline dependency resolution failed')
