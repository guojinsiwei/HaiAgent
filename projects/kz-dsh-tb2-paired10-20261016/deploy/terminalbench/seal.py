"""Seal current sources, successful Linux suites and a new real lifecycle."""
import hashlib,json,tarfile
from pathlib import Path
from experiment import validate_protocol
from storage import atomic_json
from validate_offline import source_hashes
ROOT=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def require(condition,message):
    if not condition:raise RuntimeError(message)

def main():
    validate_protocol(ROOT)
    report=json.loads((ROOT/'validation.json').read_text())
    require(report.get('passed') and report.get('platform')=='linux','Current Linux acceptance required')
    require(report['source_hashes']==source_hashes(ROOT/'runtime/kz'),'Source drift since tests')
    require({s['suite'] for s in report['suites']}=={'node','python','deadline'},'Incomplete test suites')
    for suite in report['suites']:
        require(suite['exit_code']==0 and suite['counts'].get('tests',0)>0,'Failed or empty test suite')
        require(not suite['counts'].get('skipped') and not suite['counts'].get('cancelled'),'Skipped/cancelled Linux tests')
        require(sha(ROOT/suite['log'])==suite['log_sha256'],'Test log drift')
    result=json.loads((ROOT/'engineering-lifecycle-result.json').read_text())
    require(result.get('passed') and result.get('paid_calls')==0,'New official keyless lifecycle required')
    require(result.get('lifecycle',{}).get('schema_version')==2 and result['lifecycle'].get('stage')=='cleanup_succeeded','Old lifecycle cannot seal new release')
    require(result.get('source_hashes')==report['source_hashes'],'Lifecycle tested different source')
    require(result.get('runtime_sha256')==sha(ROOT/'runtime-final.tar.gz'),'Lifecycle tested different runtime')
    baseline=json.loads((ROOT/'baseline-lifecycle-result.json').read_text())
    require(baseline.get('passed') and baseline.get('paid_calls')==0 and baseline.get('arm')=='dsh','Pure DSH keyless lifecycle required')
    require(baseline.get('source_hashes')==report['source_hashes'] and baseline.get('runtime_sha256')==sha(ROOT/'runtime-final.tar.gz'),'Pure DSH lifecycle drift')
    with tarfile.open(ROOT/'source.tar.gz') as archive:
        for member in archive.getmembers():
            if member.isfile():require((ROOT/'runtime/kz'/member.name).read_bytes()==archive.extractfile(member).read(),'Source/runtime mismatch')
    protocol=json.loads((ROOT/'protocol.json').read_text())
    require(protocol['source_sha256']==sha(ROOT/'source.tar.gz'),'Protocol source hash drift')
    for name,digest in protocol['common_hashes'].items():
        require(sha(ROOT/'runtime/kz'/name)==digest,'Frozen common runtime drift')
    protocol.update(status='offline_accepted_model_not_started',engineering_revision='engineering-1')
    atomic_json(ROOT/'protocol.json',protocol)
    names=[p for p in ROOT.iterdir() if p.suffix in ('.py','.mjs')]
    names += [ROOT/n for n in ('source.tar.gz','runtime-final.tar.gz','tasks.json','history.json','protocol.json','experiment.json','validation.json','engineering-lifecycle-result.json','budget-profile.json')]
    names += [ROOT/s['log'] for s in report['suites']]
    names += sorted((ROOT/'environment-locks').glob('*.json'))
    names += [ROOT/'dependencies/ready.json']
    names += [ROOT/'baseline-lifecycle-result.json']
    atomic_json(ROOT/'ready.json',dict(passed=True,behavior='evidence-control-3',engineering_revision='engineering-1',version='0.3.2',paid_calls=0,model_acceptance=False,files={p.relative_to(ROOT).as_posix():sha(p) for p in names}))

if __name__=='__main__':main()
