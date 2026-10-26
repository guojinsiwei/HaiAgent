"""Real cached task image, original nobody user, no external networking/model."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parent
BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')
image='98f570403ec0'
name='tb4-runtime-repair-20261015-offline'
def run(*args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=180,**kw)
ident=run('docker','create','--network','none','--name',name,'--label','kz.offline-repair=20261015','--user','0',image,'sleep','infinity').stdout.strip()
report=dict(passed=False,paid_model_calls=0,network='none',image=image,container=ident)
try:
    run('docker','start',ident)
    run('docker','cp',str(BASE/'runtime-final.tar.gz'),ident+':/tmp/dsh-runtime.tar.gz')
    run('docker','cp',str(ROOT/'native/legacy-runtime.tar.gz'),ident+':/tmp/native-runtime.tar.gz')
    run('docker','exec',ident,'sh','-c','mkdir -p /opt /logs/agent && tar -xzf /tmp/dsh-runtime.tar.gz -C /opt && tar -xzf /tmp/native-runtime.tar.gz -C /opt && chown 65534:65534 /logs/agent && chmod 555 /app && test -c /dev/null && chmod 666 /dev/null')
    result=run('docker','exec','-u','65534:65534','-w','/app',ident,'sh','-c','test ! -w /app && test -w /logs/agent && test -w /dev/null && /opt/node/bin/node --version && python3 /opt/kz-standalone/fixture.py && cd /opt/kz-standalone && python3 -m unittest -v test_provider_policy test_native_repair test_bridge test_wire_live')
    (ROOT/'container-smoke.log').write_text(result.stdout+result.stderr)
    report['passed']=True
except subprocess.CalledProcessError as error:
    (ROOT/'container-smoke.log').write_text((error.stdout or '')+(error.stderr or ''))
    raise
finally:
    (ROOT/'container-smoke.json').write_text(json.dumps(report,indent=2))
    # Remove only this script's newly created disposable fixture container.
    run('docker','rm','-f',ident)
print(json.dumps(report))
