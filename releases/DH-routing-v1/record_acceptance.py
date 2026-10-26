"""Run offline tests and seal actual results; never substitutes expected counts."""
import hashlib
import io
import json
from pathlib import Path
import platform
import time
import unittest

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'DH-subgoal-v1'
SOURCE=ROOT/'sources/bestfgs-project/src/bestfgs'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    hashes={p.name:sha(p) for p in sorted(SOURCE.glob('*.py'))}
    base=BASE/'sources/bestfgs-project/src/bestfgs'
    changed=[name for name,value in hashes.items() if not (base/name).exists() or sha(base/name)!=value]
    assert set(changed)=={'error_routing.py','lean_runtime.py'},changed
    stream=io.StringIO();began=time.time()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
    (evidence/'offline-tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    record={'release':'DH-routing-v1','base':str(BASE),'date':'2026-10-08',
        'platform':platform.platform(),'tests_run':result.testsRun,
        'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'skips':[(str(test),reason) for test,reason in result.skipped],
        'successful':result.wasSuccessful(),'seconds':time.time()-began,
        'routing_tests':13,'changed_modules':changed,'source_hashes':hashes,
        'test_sha256':sha(ROOT/'tests/test_error_routing.py'),
        'paid_model_calls':0,'remote_deployment':False,'live_experiments_modified':False,
        'score_improvement_validated':False,
        'scope':'release regression suite plus new subgoal cases; not all legacy source tests'}
    save(evidence/'routing-acceptance.json',record)
    save(ROOT/'dh-source-manifest.json',{'release':'DH-routing-v1','base':'DH-subgoal-v1',
        'feature_flag':'RoutingPolicy','hashes':hashes,
        'base_hashes':{p.name:sha(p) for p in sorted(base.glob('*.py'))}})
    print(json.dumps({k:v for k,v in record.items() if k not in {'source_hashes','base','skips'}}))
    if not result.wasSuccessful():raise SystemExit(1)

if __name__=='__main__':main()
