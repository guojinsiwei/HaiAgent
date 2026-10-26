"""Verify carried official results and unchanged method code before freezing repair."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import control
from control import HERE, plan, source_hashes
from audit import verify
from prepare import write, reserve

OLD=HERE.with_name('lhtb-triple12-v161-20260927-r2')

def main():
    if (HERE/'health.json').exists(): raise RuntimeError('Already started')
    health=json.loads((OLD/'health.json').read_text())
    assert health['state']=='needs_attention' and not health['active']
    rows=json.loads((OLD/'summary.json').read_text())
    assert len(rows)==11 and len({(r['task'],r['method']) for r in rows})==11
    allowed_roots=[OLD.resolve(),OLD.with_name('lhtb-triple25-v161-20260926').resolve()]
    for row in rows:
        path=Path(row['report']).resolve()
        assert any(path.is_relative_to(root/'runs') for root in allowed_roots)
        report=json.loads(path.read_text())
        assert row['process_exit_code']==0 and not report.get('exception_info') and report.get('verifier_result') is not None
        assert row['verifier_result']==report['verifier_result']
        assert verify(path.parent/'agent/audit.jsonl')==row['audit_chain']
        row.setdefault('origin_protocol_sha256',health['protocol_sha256'])
    for name in ('bestfgs-project/src','hai-project/src','upstream/harbor/src'):
        for p in (OLD/name).rglob('*.py'):
            assert p.read_bytes()==(HERE/p.relative_to(OLD)).read_bytes()
    write(HERE/'prior-results.json',rows)
    subprocess.run([sys.executable,'-B','-m','unittest','test_outcomes','test_durable'],cwd=HERE,check=True)
    reserve()
    plan()
    hashes=source_hashes()
    ready={'ready':True,'source_hashes':hashes,'protocol_sha256':hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest(),
        'sealed_at':time.time(),'model_calls':0,'carried':11,'new_attempts':25,
        'original_fixture_protocol':health['protocol_sha256']}
    write(HERE/'ready.json',ready)
    print(json.dumps({k:v for k,v in ready.items() if k!='source_hashes'}))

if __name__=='__main__': main()
