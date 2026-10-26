"""One hidden credential entry; five independent detached processes, RAM only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
ROOT=Path(__file__).resolve().parent


def validate():
    manifest=json.loads((ROOT/'resume-manifest.json').read_text())
    for arm in manifest['arms']:
        root=Path(arm['root']);ready=json.loads((root/'resume-ready.json').read_text())
        assert ready['ready'] and ready['paid_model_calls']==0
        for name,expected in ready['hashes'].items():
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,name
        assert not (root/'launch.claim').exists(),f'Already launched {root.name}'
    return manifest


def main():
    manifest=validate()
    if '--check' in sys.argv:
        print(json.dumps({'ready':True,'preserved':manifest['preserved'],'remaining':manifest['rerun']}));return
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    req=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a):return None
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as r:models=json.load(r)
    assert any(m['id']=='deepseek-flash' for m in models['data'])
    rows=[]
    for arm in manifest['arms']:
        root=Path(arm['root'])
        os.close(os.open(root/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
        python=str(Path(arm['source'])/'runtime/bin/python') if arm['method']=='retrac' else sys.executable
        with (root/'worker.log').open('x') as out,(root/'worker-stderr.log').open('x') as err:
            child=subprocess.Popen([python,'-B',str(root/'resume_worker.py')],cwd=root,
                stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True,text=True)
            child.stdin.write(key+'\n');child.stdin.close()
        record={'method':arm['method'],'pid':child.pid,'time':time.time(),'remaining':len(arm['run_tasks'])}
        (root/'launch.json').write_text(json.dumps(record));rows.append(record)
    (ROOT/'launch.json').write_text(json.dumps({'started':rows,'time':time.time()}))
    print(json.dumps({'state':'started','arms':rows}))

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'state':'launch_failed','error_type':type(exc).__name__}),file=sys.stderr)
        raise SystemExit(1)
