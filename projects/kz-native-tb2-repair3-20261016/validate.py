import subprocess,sys,os,json,hashlib
from pathlib import Path
from storage import atomic_json
ROOT=Path(__file__).resolve().parent
NODE='/mnt/sdb/home/lizh639/tb2-kz-dsh-paired10-20261016/runtime/node/bin/node'
def hashes():
    paths=list(ROOT.glob('*.py'))+[ROOT/'experiment.json']+list((ROOT/'native').rglob('*.py'))+list((ROOT/'native').rglob('*.mjs'))
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if '__pycache__' not in p.parts}
def main():
    before=hashes();results=[]
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    for k in list(env):
        if k.endswith(('API_KEY','AUTH_TOKEN')):env.pop(k)
    for name,cmd,cwd in [('deployment',[sys.executable,'-m','unittest','discover','-s',str(ROOT),'-p','test_*.py','-v'],ROOT),
        ('native',[sys.executable,'-m','unittest','-v','test_native_repair','test_bridge','test_provider_policy','test_wire_live'],ROOT/'native'),
        ('fixture',[sys.executable,'fixture.py'],ROOT/'native'),
        ('deadline',[NODE,'--test','test_deadline.mjs'],ROOT/'native'),
        ('historical',[sys.executable,'regression_probe.py','legacy'],ROOT/'native')]:
        with (ROOT/(name+'-tests.log')).open('w') as out:run=subprocess.run(cmd,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=600)
        passed=run.returncode==0
        if name=='historical':
            observed=json.loads((ROOT/(name+'-tests.log')).read_text().splitlines()[-1])
            expected=json.loads((ROOT/'historical-regression.json').read_text())['baseline_regression']['repaired']
            passed=observed==expected
        results.append(dict(suite=name,exit_code=run.returncode,passed=passed))
    report=dict(passed=all(x['passed'] for x in results) and before==hashes(),suites=results,source_hashes=before,paid_calls=0,historical_note='Five previously recorded historical expectation failures retained; no new regression allowed.')
    atomic_json(ROOT/'validation.json',report);print(json.dumps({k:v for k,v in report.items() if k!='source_hashes'}));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
