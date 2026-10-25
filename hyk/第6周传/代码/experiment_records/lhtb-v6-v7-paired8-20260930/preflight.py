"""Seal paired tasks/sources only after both official continuation fixtures pass."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from control import HERE,METHODS,source_hashes,verify_image,environment,PYTHON
from prepare import reserve,write,COMMIT
from prepare_paired import verify_releases
from audit import verify

def main():
    if (HERE/'health.json').exists() or (HERE/'ready.json').exists():raise RuntimeError('Never reseal started/sealed run')
    reserve()
    if subprocess.check_output(['git','-C',str(HERE/'upstream'),'rev-parse','HEAD'],text=True).strip()!=COMMIT:
        raise RuntimeError('Benchmark commit mismatch')
    if verify_releases()!=json.loads((HERE/'release-source-verification.json').read_text()):
        raise RuntimeError('Release verification changed')
    manifest=json.loads((HERE/'manifest.json').read_text())
    for row in manifest['tasks']:verify_image(row['task'])
    fixtures={};imports={}
    for arm in METHODS:
        reports=list((HERE/'fixtures'/('fixture8-'+arm+'-fixture')).glob('*/result.json'))
        if len(reports)!=1:raise RuntimeError('Missing official fixture: '+arm)
        report=json.loads(reports[0].read_text());reward=(report.get('verifier_result') or {}).get('rewards') or {}
        if report.get('exception_info') or not reward or min(reward.values())<1:
            raise RuntimeError('Fixture did not pass: '+arm)
        if (report.get('agent_result') or {}).get('metadata',{}).get('continue_until_timeout_phases',0)<1:
            raise RuntimeError('Continuation was not exercised')
        path=reports[0].parent/'agent/audit.jsonl';fixtures[arm]=verify(path)
        events=[json.loads(s) for s in path.read_text().splitlines()]
        if not any(e.get('event')=='method_end' and e.get('stop_reason')=='wall_budget_exhausted' for e in events):
            raise RuntimeError('Budget delivery not exercised')
        probe="import json,transport,bestfgs.lean_runtime as r; print(json.dumps({'adapter':transport.__file__,'runtime':r.__file__}))"
        paths=json.loads(subprocess.check_output([PYTHON,'-B','-c',probe],cwd=HERE,env=environment(arm),text=True))
        if any(not Path(p).resolve().is_relative_to(HERE/'arms'/arm) for p in paths.values()):
            raise RuntimeError('Arm import crossed source boundary')
        imports[arm]=paths
    hashes=source_hashes()
    result=dict(ready=True,source_hashes=hashes,fixture_audits=fixtures,arm_imports=imports,
        protocol_sha256=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),sealed_at=time.time(),
        model_calls=0,tasks_per_arm=8,total_trials=16,disk_reserve_gib=120)
    write(HERE/'ready.json',result)
    print(json.dumps(dict(ready=True,protocol_sha256=result['protocol_sha256'],arm_imports=imports,model_calls=0)))

if __name__=='__main__':main()
