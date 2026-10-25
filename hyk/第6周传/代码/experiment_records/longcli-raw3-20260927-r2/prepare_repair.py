"""Prepare independent repair revision from stopped predecessor; no real API calls."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.with_name('longcli-raw3-20260927')
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert json.loads((OLD/'health.json').read_text())['state']=='failed'
    assert not (HERE/'health.json').exists()
    for name in ['runtime', 'tools', 'roots']:
        shutil.copytree(OLD/name, HERE/name, symlinks=True)
    shutil.copy2(OLD/'runs/cs61_fa24_scheme/events.jsonl', HERE/'prior-scheme-events.jsonl')
    protocol = json.loads((OLD/'protocol.json').read_text())
    protocol['version'] = 'longcli-raw3-diagnostic-r2'
    protocol['repair'] = {'origin': str(OLD), 'prior_trace_sha256': sha(HERE/'prior-scheme-events.jsonl'),
                         'resume': 'Replay recorded responses/results without API/tool execution; assert next context matches.',
                         'wall_accounting': 'Subtract prior active wall time; replay overhead and recovery waits count.',
                         'transport_recovery': 'Up to 3 extra cycles per request, 6 per task, 10/30/60 s backoff; 2 attempts per cycle. No auth/format retries.'}
    (HERE/'protocol.json').write_text(json.dumps(protocol, indent=2))
    for task in protocol['tasks']:
        root = HERE/'roots'/task
        for name, minor in [('null',3),('zero',5),('random',8),('urandom',9)]:
            path = root/'dev'/name
            if path.exists():
                assert stat.S_ISCHR(path.lstat().st_mode), 'Unexpected existing device entry'
                assert path.stat().st_rdev==os.makedev(1,minor)
            else:
                os.mknod(path, stat.S_IFCHR|0o666, os.makedev(1,minor))
            os.chmod(path,0o666)
        for base in [root/'app', root/'tmp']:
            for parent, dirs, files in os.walk(base,followlinks=False):
                os.chown(parent,65534,65534,follow_symlinks=False)
                for name in dirs+files:
                    os.chown(Path(parent)/name,65534,65534,follow_symlinks=False)
    from runner import SandboxExecutor, Config, Task, run_one
    checks=[]
    for task in protocol['tasks']:
        root=HERE/'roots'/task
        config=Config(method='raw')
        executor=SandboxExecutor(Task(task,'Probe',root/'app',delivery='terminal'),config,root)
        command={'argv':['bash','-lc', 'printf check >/dev/null && python3 -c \'import os; assert open("/dev/null","rb").read()==b""; assert open("/dev/zero","rb").read(8)==bytes(8); assert len(os.urandom(8))==8; print("devices-ok")\''],
                 'cwd':'.','timeout_seconds':15,'stdin':None}
        result=executor.execute(command,time.monotonic()+20)
        assert result.exit_code==0 and 'devices-ok' in result.stdout and not result.stderr, result.payload()
        checks.append({'task':task,'devices_ok':True})
    result=run_one('cs61_fa24_scheme','OFFLINE-PLACEHOLDER',resume_test=True)
    assert result['submitted'] and result['tool_calls']==29
    events=[json.loads(s) for s in (HERE/'resume-fixture/cs61_fa24_scheme/events.jsonl').read_text().splitlines()]
    assert any(e['event']=='resume_context_verified' for e in events)
    assert not any(e['event']=='api_start' for e in events)
    assert len([e for e in events if e['event']=='replayed_tool'])==29
    (HERE/'repair-checks.json').write_text(json.dumps({'devices':checks,'resume_verified':True,'model_calls':0},indent=2))
    hashes={str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*.py') if p.parent==HERE or p.is_relative_to(HERE/'runtime')}
    for name in ['protocol.json','prior-scheme-events.jsonl','repair-checks.json']:
        hashes[name]=sha(HERE/name)
    for p in (HERE/'tools/extracted').rglob('*'):
        if p.is_file() and not p.is_symlink(): hashes[str(p.relative_to(HERE))]=sha(p)
    (HERE/'ready.json').write_text(json.dumps({'ready':True,'hashes':hashes,'model_calls':0},indent=2))
    print(json.dumps({'ready':True,'resume_turns':29,'model_calls':0}),flush=True)

if __name__=='__main__': main()
