"""Seal only after the Linux regressions AND real keyless Harbor trial pass."""
import hashlib,json,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/tmp/lizh639-tb4-kz-dsh-unlimited-repair-20261014')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    node=(ROOT/'node-tests-final.log').read_text()
    assert 'tests 371' in node and 'pass 371' in node and 'fail 0' in node and 'skipped 0' in node
    assert 'Ran 15 tests' in (ROOT/'python-tests-final.log').read_text() and '\nOK\n' in (ROOT/'python-tests-final.log').read_text()
    assert 'pass 2' in (ROOT/'deadline-tests.log').read_text() and 'fail 0' in (ROOT/'deadline-tests.log').read_text()
    assert 'Pinned package versions match' in (ROOT/'host-check.log').read_text()
    result=json.loads((ROOT/'ec2-lifecycle-final-result.json').read_text());assert result['passed'] and result['paid_calls']==0
    with tarfile.open(ROOT/'source.tar.gz') as archive:
        for member in archive.getmembers():
            if member.isfile():assert (ROOT/'runtime/kz'/member.name).read_bytes()==archive.extractfile(member).read(),member.name
    protocol=json.loads((ROOT/'protocol.json').read_text())
    with tarfile.open(BASE/'runtime-final.tar.gz') as archive:
        for name,h in protocol['common_hashes'].items():
            assert sha(ROOT/'runtime/kz'/name)==h
            assert hashlib.sha256(archive.extractfile('kz/'+name).read()).hexdigest()==h
    protocol.update(status='offline_accepted_model_not_started',paired_tasks=None,max_trials_with_retry=20,source_sha256=sha(ROOT/'source.tar.gz'),
        acceptance='371 Linux DSH/model-fixture tests; 15 Python fault/queue tests; 2 process deadline tests; real keyless official payments lifecycle')
    (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    names=[p for p in ROOT.iterdir() if p.suffix in ('.py','.mjs')]
    names += [ROOT/n for n in ('source.tar.gz','runtime-final.tar.gz','tasks.json','history.json','protocol.json','node-tests-final.log','python-tests-final.log','deadline-tests.log','host-check.log','ec2-lifecycle-final-result.json')]
    names += sorted((ROOT/'environment-locks').glob('*.json'))
    ready=dict(passed=True,behavior='evidence-control-2',version='0.3.1',paid_calls=0,model_acceptance=False,
        files={str(p.relative_to(ROOT)):sha(p) for p in names})
    (ROOT/'ready.json').write_text(json.dumps(ready,indent=2));print(json.dumps(dict(passed=True,sealed_files=len(names),paid_calls=0)))
if __name__=='__main__':main()
