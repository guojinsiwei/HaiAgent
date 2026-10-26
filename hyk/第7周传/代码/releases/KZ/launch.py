"""Fresh encrypted stdin credential, sealed inputs, no secret files/logs."""
import json
import os
import subprocess
import sys
import time
from common import ROOT, save, validate


def main():
    from verify_contract import verify
    verify()  # Reject an old hard-stop source before reading/sending credentials.
    p = validate()
    assert not (ROOT/'launch.claim').exists(), 'Already launched; inspect status'
    if '--check' in sys.argv:
        print(json.dumps(dict(ready=True, trials=len(p['tasks']), preserved=7,
                             concurrency=p['concurrency'], model=p['model'])))
        return
    key = sys.stdin.readline().strip()
    assert key and not any(c.isspace() for c in key)
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    req = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization': 'Bearer '+key})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
        listing = json.load(response)
    assert any(m['id'] == p['model'] for m in listing['data'])
    os.close(os.open(ROOT/'launch.claim', os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600))
    with (ROOT/'worker.log').open('x') as out, (ROOT/'worker-stderr.log').open('x') as err:
        child = subprocess.Popen([sys.executable, '-B', str(ROOT/'supervisor.py')], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=out, stderr=err, start_new_session=True, text=True)
        child.stdin.write(key+'\n'); child.stdin.close()
    save(ROOT/'launch.json', dict(pid=child.pid, time=time.time(), trials=13, preserved=7,
                                 credential='fresh input; RAM only; SSH stdin'))
    print(json.dumps(dict(started=True, pid=child.pid, trials=13, preserved=7, concurrency=6)))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(json.dumps(dict(state='launch_failed', error_type=type(e).__name__)))
        raise SystemExit(1)
