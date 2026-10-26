"""Prepare an isolated AppWorld installation and public assets; zero model calls."""
from pathlib import Path
import json, subprocess, sys, time, urllib.request
R=Path(__file__).resolve().parent
assert R.name=='appworld-three-arm30-20261018'
def run(args,timeout=1200):
    print('RUN',args,flush=True)
    subprocess.run(list(map(str,args)),check=True,timeout=timeout,cwd=R)
if not (R/'package-version.json').exists():
    with urllib.request.urlopen('https://pypi.org/pypi/appworld/json',timeout=30) as f: meta=json.load(f)
    (R/'package-version.json').write_text(json.dumps({'version':meta['info']['version'],'selected_at':time.time()}))
version=json.loads((R/'package-version.json').read_text())['version']
import os
context=R/'image-context';context.mkdir(exist_ok=True)
(context/'Dockerfile').write_text('FROM python:3.12-slim-bookworm\nRUN apt-get update && apt-get install -y --no-install-recommends gcc g++ make git ca-certificates && rm -rf /var/lib/apt/lists/*\nRUN pip install --disable-pip-version-check appworld=='+version+'\nRUN appworld install\nRUN python -m venv /opt/recuris && /opt/recuris/bin/pip install pydantic==2.13.5\nWORKDIR /appworld\nENV APPWORLD_ROOT=/appworld\n')
tag='appworld-three-arm30:20261018'
run(['docker','build','--label','experiment='+R.name,'-t',tag,context],timeout=2400)
image=subprocess.check_output(['docker','image','inspect',tag,'--format','{{.Id}}'],text=True).strip()
(R/'image.json').write_text(json.dumps({'image':image,'tag':tag,'appworld_version':version}))
assets=R/'assets';assets.mkdir(exist_ok=True)
run(['docker','run','--rm','--label','experiment='+R.name,'--user',f'{os.getuid()}:{os.getgid()}','-e','HOME=/tmp','-v',f'{assets}:/appworld',image,'appworld','download','data'],timeout=2400)
(R/'installed-packages.txt').write_text(subprocess.check_output(['docker','run','--rm','--network','none',image,'pip','freeze'],text=True))
print('APPWORLD_BOOTSTRAP_COMPLETE',flush=True)
