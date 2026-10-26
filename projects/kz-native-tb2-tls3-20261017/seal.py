import hashlib,json,tarfile
from pathlib import Path
from storage import atomic_json
from validate import hashes
from experiment import validate_protocol
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    validate_protocol(ROOT)
    v=json.loads((ROOT/'validation.json').read_text());a=json.loads((ROOT/'accept-timeout-result.json').read_text())
    assert v['passed'] and v['source_hashes']==hashes()
    assert a['source_hashes']==v['source_hashes']
    assert a['passed'] and a['paid_calls']==0 and a['runtime_sha256']==sha(ROOT/'native-runtime.tar.gz')
    with tarfile.open(ROOT/'native-runtime.tar.gz') as archive:
        for m in archive.getmembers():
            if m.isfile():assert (ROOT/'native'/Path(*Path(m.name).parts[1:])).read_bytes()==archive.extractfile(m).read()
    names=list(ROOT.glob('*.py'))+[ROOT/n for n in ('native-runtime.tar.gz','python-runtime.tar.gz','python-source.json','runtime-final.tar.gz','protocol.json','experiment.json','budget-profile.json','validation.json','tasks.json','history.json','accept-timeout-result.json','historical-regression.json','parent-results.json','budget-migration.json','ca-provenance.json','verifier-deps.tar.gz','verifier-deps-provenance.json')]
    names+=list(ROOT.glob('*-tests.log'))+list((ROOT/'environment-locks').glob('*.json'))
    atomic_json(ROOT/'ready.json',dict(passed=True,paid_calls=0,variant='Native KZ2.0 repair1 with TB2 bounded runtime',files={p.relative_to(ROOT).as_posix():sha(p) for p in names}))
    print('SEALED')
if __name__=='__main__':main()
