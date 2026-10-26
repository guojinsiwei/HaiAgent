"""Prepare infrastructure only after solver collection, before official grading."""
import hashlib,json,importlib.util,threading,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TASKS={'build-cython-ext','qemu-alpine-ssh','qemu-startup','regex-log','sqlite-with-gcov'}
@contextlib.contextmanager
def verifier_network(verifier):
 spec=importlib.util.spec_from_file_location('verifier_egress_proxy',ROOT/'dependencies/network_proxy.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 server=module.ThreadingHTTPServer((module.HOST,0),module.Handler)
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 proxy='http://%s:%d'%server.server_address
 old=dict(verifier.verifier_env or {})
 verifier.verifier_env=dict(old,HTTP_PROXY=proxy,HTTPS_PROXY=proxy,http_proxy=proxy,https_proxy=proxy,NO_PROXY='localhost,127.0.0.1,::1',no_proxy='localhost,127.0.0.1,::1')
 try:yield
 finally:server.shutdown();server.server_close();worker.join(timeout=5);verifier.verifier_env=old

def validate_test_report(verifier):
 report=json.loads((verifier.trial_paths.verifier_dir/'ctrf.json').read_text())
 result=report.get('results',{});summary=result.get('summary',{})
 if type(summary.get('tests')) is not int or summary['tests']<=0 or len(result.get('tests',[]))!=summary['tests']:
  raise RuntimeError('Official tests did not execute; cannot treat infrastructure failure as score zero')

async def prepare_verifier(verifier):
 name=verifier.task.paths.task_dir.name
 approved={t['name'] for t in json.loads((ROOT/'tasks.json').read_text())['tasks']}
 if name not in approved:raise RuntimeError('Task outside frozen selection')
 script=(verifier.task.paths.task_dir/'tests/test.sh').read_text()
 # Only bootstrap the matching official uv installer; other recipes run unchanged.
 if 'astral.sh/uv/0.9.5' not in script:return
 env=verifier.environment
 provenance=json.loads((ROOT/'verifier-deps-provenance.json').read_text())
 if hashlib.sha256((ROOT/'verifier-deps.tar.gz').read_bytes()).hexdigest()!=provenance['archive_sha256']:raise RuntimeError('Verifier dependency archive drift')
 await env.upload_file(ROOT/'verifier-deps.tar.gz','/tmp/kz-verifier-deps.tar.gz')
 command="""set -eu
test ! -L /opt/kz-verifier
mkdir -p /opt/kz-verifier
tar -xzf /tmp/kz-verifier-deps.tar.gz -C /opt/kz-verifier
printf 'Acquire::http::No-Cache "true";\nAcquire::https::No-Cache "true";\nAcquire::Retries "3";\nAcquire::http::Timeout "45";\nAcquire::https::Timeout "45";\n' > /etc/apt/apt.conf.d/99-kz-verifier-network
find /etc/apt/sources.list.d -type f -exec sed -i 's|http://deb.debian.org|https://mirrors.ustc.edu.cn|g; s|https://deb.debian.org|https://mirrors.ustc.edu.cn|g; s|http://security.debian.org|https://mirrors.ustc.edu.cn/debian-security|g' {} +
if test -f /etc/apt/sources.list; then sed -i 's|http://deb.debian.org|https://mirrors.ustc.edu.cn|g; s|https://deb.debian.org|https://mirrors.ustc.edu.cn|g; s|http://security.debian.org|https://mirrors.ustc.edu.cn/debian-security|g' /etc/apt/sources.list; fi
if grep -q '^VERSION_CODENAME=bullseye$' /etc/os-release; then
  # The security index references removed curl/nghttp2 files. Select the still
  # available signed bullseye release versions for verifier download tooling.
  printf 'Package: curl libcurl4 libnghttp2-14\nPin: release n=bullseye\nPin-Priority: 990\n' > /etc/apt/preferences.d/kz-verifier-download-tools
fi
apt-get update
apt-get install -y curl
"""
 result=await env.exec(command=command,user='root',env=verifier.verifier_env,timeout_sec=360)
 (verifier.trial_paths.verifier_dir/'infrastructure-bootstrap.log').write_text((result.stdout or '')+'\n'+(result.stderr or ''))
 if result.return_code:raise RuntimeError('Verifier infrastructure bootstrap failed')
 verifier.verifier_env=dict(verifier.verifier_env or {},UV_DOWNLOAD_URL='file:///opt/kz-verifier/downloads',UV_PYTHON_INSTALL_DIR='/opt/kz-verifier/python',UV_HTTP_TIMEOUT='90',UV_INDEX_URL='https://mirrors.ustc.edu.cn/pypi/simple',PIP_INDEX_URL='https://mirrors.ustc.edu.cn/pypi/simple')
