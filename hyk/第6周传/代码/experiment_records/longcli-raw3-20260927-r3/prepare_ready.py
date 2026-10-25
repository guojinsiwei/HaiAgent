import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
OLD=HERE.with_name('longcli-raw3-20260927-r2')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert not (HERE/'health.json').exists()
    assert json.loads((OLD/'health.json').read_text())['state']=='failed'
    protocol=json.loads((OLD/'protocol.json').read_text())
    protocol['version']='longcli-raw3-diagnostic-r3'
    protocol['repair_r3']={'origin':str(OLD),'carried_tool_calls':569,
        'recovery':'Per-request up to 8 extra retry cycles, max 900-second episode within original task wall budget; never retry auth/certificate/protocol errors.',
        'dns':'300-second fresh cache; last known resolved addresses usable up to 1800 seconds only after DNS error, unchanged HTTPS host/SNI/certificate verification.',
        'resume':'Replay original 29 and r2 actual 540 responses, all 569 recorded results; assert next context and final workspace hash; no API/tool execution during replay.',
        'old_logs_preserved':True,'model_policy_changed':False}
    (HERE/'protocol.json').write_text(json.dumps(protocol,indent=2))
    subprocess.run([sys.executable,'-B','-m','unittest','test_transport'],cwd=HERE,check=True)
    from runner import run_one
    if '--seal-after-supervision-test' not in sys.argv:
        result=run_one('cs61_fa24_scheme','OFFLINE-PLACEHOLDER',resume_test=True)
        assert result['submitted'] and result['tool_calls']==569,result
    else:
        old_ready=json.loads((HERE/'ready.json').read_text())
        for name in ['runner.py','runtime/haiagent/runtime.py','prior-scheme-events.jsonl','origin-scheme-events.jsonl']:
            assert sha(HERE/name)==old_ready['hashes'][name], 'Cannot reuse replay check after replay/source change'
    subprocess.run([sys.executable,'-B','test_restart_integration.py'],cwd=HERE,check=True)
    events=[json.loads(s) for s in (HERE/'resume-fixture/cs61_fa24_scheme/events.jsonl').read_text().splitlines()]
    assert any(e['event']=='resume_context_verified' for e in events)
    assert not any(e['event']=='api_start' for e in events)
    assert len([e for e in events if e['event']=='replayed_tool'])==569
    checks={'resume_verified':True,'replayed_tools':569,'real_model_calls':0,'real_tool_calls':0,
        'prior_active_wall_seconds':next(e['prior_wall_seconds'] for e in events if e['event']=='resume_context_verified')}
    (HERE/'repair-checks.json').write_text(json.dumps(checks,indent=2))
    hashes={str(p.relative_to(HERE)):sha(p) for p in HERE.rglob('*.py') if p.parent==HERE or p.is_relative_to(HERE/'runtime')}
    for name in ['protocol.json','prior-scheme-events.jsonl','origin-scheme-events.jsonl','repair-checks.json']:
        hashes[name]=sha(HERE/name)
    for p in (HERE/'tools/extracted').rglob('*'):
        if p.is_file() and not p.is_symlink(): hashes[str(p.relative_to(HERE))]=sha(p)
    (HERE/'ready.json').write_text(json.dumps({'ready':True,'hashes':hashes,'model_calls':0},indent=2))
    print(json.dumps({'ready':True,**checks}),flush=True)

if __name__=='__main__': main()
