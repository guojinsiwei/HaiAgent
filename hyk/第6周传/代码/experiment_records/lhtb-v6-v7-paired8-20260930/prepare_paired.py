"""Prepare one paired run using frozen releases and the fixed prior task order."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from prepare import HERE,COMMIT,select,write,reserve

BASE=Path('/var/tmp/lizh639-lhtb-bestfgs12-memory-v5-20260930')
RELEASES={'v6':Path('/var/tmp/lizh639-monitor-control-v6'),'v7':Path('/var/tmp/lizh639-route-selection-v7')}

def verify_releases():
    verified={}
    for arm,release in RELEASES.items():
        destination=HERE/'arms'/arm
        expected=json.loads((release/'fixed-source-manifest.json').read_text())
        integration=json.loads((release/'integration-source-manifest.json').read_text())
        expected=dict(expected,**{'transport.py':integration['transport.py']})
        actual={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in destination.rglob('*.py')}
        if actual!=expected:raise RuntimeError('Frozen arm source mismatch: '+arm)
        verified[arm]=dict(release=str(release),hashes=actual)
    for name in ('audit.py','docker_state.py','container_command.py','hai_outcomes.py'):
        raw=(HERE/name).read_bytes()
        if any(raw!=(r/'sources'/name).read_bytes() for r in RELEASES.values()):
            raise RuntimeError('Unequal shared infrastructure: '+name)
    if any((HERE/'outcomes.py').read_bytes()!=(r/'integration/outcomes.py').read_bytes() for r in RELEASES.values()):
        raise RuntimeError('Unequal result classification')
    return verified

def main():
    if any((HERE/p).exists() for p in ('health.json','ready.json','arms','manifest.json')):
        raise RuntimeError('Preparation already attempted; inspect before resuming')
    reserve()
    original=json.loads((BASE/'manifest.json').read_text())
    manifest=select(original)
    write(HERE/'manifest.json',manifest);write(HERE/'prior-results.json',[])
    for name in ('upstream','fixture'):
        shutil.copytree(BASE/name,HERE/name,symlinks=True,ignore=shutil.ignore_patterns('__pycache__'))
    if subprocess.check_output(['git','-C',str(HERE/'upstream'),'rev-parse','HEAD'],text=True).strip()!=COMMIT:
        raise RuntimeError('Benchmark commit mismatch')
    for arm,release in RELEASES.items():
        shutil.copytree(release/'sources',HERE/'arms'/arm,ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(release/'integration/transport.py',HERE/'arms'/arm/'transport.py')
    selected={t['task'] for t in manifest['tasks']}
    images=[r for r in json.loads((BASE/'images.json').read_text()) if r['task'] in selected]
    if len(images)!=8:raise RuntimeError('Missing image records')
    for row in images:
        info=json.loads(subprocess.check_output(['docker','image','inspect',row['image']]))[0]
        if info['Id']!=row['id'] or not any(d.endswith('@'+row['digest']) for d in info.get('RepoDigests',[])):
            raise RuntimeError('Frozen image changed: '+row['task'])
    write(HERE/'images.json',images)
    write(HERE/'verified-digests.json',{r['image']:r['digest'] for r in images})
    write(HERE/'release-source-verification.json',verify_releases())
    write(HERE/'preparation.json',dict(state='images_ready',ready_images=8,model_calls=0,updated=time.time()))
    from control import plan
    plan()
    print(json.dumps(dict(tasks=[t['task'] for t in manifest['tasks']],total_trials=16,
        aggregate_agent_wall_hours=2*sum(t['agent']['timeout_sec'] for t in manifest['tasks'])/3600,model_calls=0)))

if __name__=='__main__':main()
