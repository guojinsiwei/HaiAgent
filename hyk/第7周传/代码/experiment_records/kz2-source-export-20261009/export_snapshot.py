"""Read-only remote source export; validate every copied byte against sealed hashes."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
CODE = ROOT / 'KZ2.0_完整源码_20261009'
ARCHIVE = ROOT / 'KZ2.0-source.tar.gz'
REMOTE = '/mnt/sdb/home/lizh639/kz2-cow-timeout-retry-20261009'
REMOTE_PROGRAM = r'''
import hashlib,io,json,sys,tarfile
from pathlib import Path
root=Path('/mnt/sdb/home/lizh639/kz2-cow-timeout-retry-20261009')
ready=json.loads((root/'ready.json').read_text()); proof=json.loads((root/'source-provenance.json').read_text())
assert ready.get('ready')
selected=[]
for folder in ('sources','compatibility','tests'):
    for p in (root/folder).rglob('*'):
        if '__pycache__' in p.parts:continue
        assert not p.is_symlink(),'Refuse source links'
        if p.is_file():
            assert p.suffix in ('.py','.txt'),str(p.relative_to(root))
            selected.append(p)
selected.extend(root.glob('*.py'))
for name in ('protocol.json','source-provenance.json','historic-config-lock.json','ready.json'):
    selected.append(root/name)
assert len(selected)==len(set(selected))
payloads={}; records=[]
for p in sorted(selected):
    name=p.relative_to(root).as_posix()
    assert not any(s in p.parts for s in ('jobs','grades','incoming','logs','host-tmp','evidence','acceptance-jobs'))
    data=p.read_bytes(); digest=hashlib.sha256(data).hexdigest()
    if name in ready['hashes']:assert digest==ready['hashes'][name],name
    if name in proof['source_hashes']:assert digest==proof['source_hashes'][name],name
    payloads[name]=data; records.append({'path':name,'bytes':len(data),'sha256':digest})
assert set(proof['source_hashes'])<=set(payloads),'Missing active source'
for name in ready['hashes']:
    if name.startswith(('sources/','compatibility/','tests/')) and name.endswith('.py'):
        assert name in payloads,name
manifest={'source':str(root),'version':'KZ2.0','revision':'cow-timeout-retry1',
          'files':records,'core_files_verified':len(proof['source_hashes']),
          'remote_writes':0,'model_api_calls':0,'credentials_or_trial_logs_included':False,
          'scope':'All exported solver modules, tests, compatibility modules and root Python adapters; no benchmark inputs/images'}
payloads['EXPORT-MANIFEST.json']=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as archive:
    for name,data in payloads.items():
        member=tarfile.TarInfo(name); member.size=len(data); member.mode=0o644
        archive.addfile(member,io.BytesIO(data))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not CODE.exists() and not ARCHIVE.exists(), 'Never overwrite an exported snapshot'
    ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-i',
           'C:/Users/54177/.ssh/cubestudio_notebook', 'lizh639@172.16.108.236',
           '/mnt/sdb/home/lizh639/terminalbench-v14-setup/runtime/bin/python -B -']
    with ARCHIVE.open('xb') as stream:
        result = subprocess.run(ssh, input=REMOTE_PROGRAM.encode('utf-8'), stdout=stream,
                                stderr=subprocess.PIPE, timeout=120)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')[-1200:]
    CODE.mkdir()
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            assert member.isfile() and not path.is_absolute() and '..' not in path.parts
        archive.extractall(CODE, filter='data')
    manifest = json.loads((CODE/'EXPORT-MANIFEST.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        assert sha(CODE/item['path']) == item['sha256'], item['path']
    assert len(list(CODE.rglob('*'))) >= len(manifest['files'])
    baseline = WORKSPACE/'experiment_records/longcli-dh-raw-full20-20261004'
    core = baseline/'sources/bestfgs-project/src/bestfgs'
    origin = json.loads((baseline/'dh-source-manifest.json').read_text(encoding='utf-8'))
    for name, digest in origin['hashes'].items():
        assert sha(core/name) == digest, 'Frozen v9 changed: '+name
    latest = CODE/'sources/bestfgs-project/src/bestfgs'
    old_files = {p.name:sha(p) for p in core.glob('*.py')}
    new_files = {p.name:sha(p) for p in latest.glob('*.py')}
    comparison = {'v9_reference':str(baseline),'v9_identity':origin['base'],
                  'v9_source_manifest_sha256':sha(baseline/'dh-source-manifest.json'),
                  'kz2_reference':REMOTE,'kz2_revision':manifest['revision'],
                  'added_modules':sorted(set(new_files)-set(old_files)),
                  'removed_modules':sorted(set(old_files)-set(new_files)),
                  'changed_modules':sorted(n for n in old_files.keys()&new_files.keys() if old_files[n]!=new_files[n]),
                  'unchanged_modules':sorted(n for n in old_files.keys()&new_files.keys() if old_files[n]==new_files[n]),
                  'latest_protocol':json.loads((CODE/'protocol.json').read_text(encoding='utf-8')),
                  'v9_protocol':json.loads((baseline/'protocol.json').read_text(encoding='utf-8'))}
    (CODE/'V9-COMPARISON.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'exported':str(CODE),'files':len(manifest['files']),
        'verified_core_files':manifest['core_files_verified'],'bytes':sum(r['bytes'] for r in manifest['files']),
        'v9_source_verified':True,'added_modules':comparison['added_modules'],
        'changed_modules':comparison['changed_modules'],'paid_model_calls':0,'remote_writes':0},ensure_ascii=False))


if __name__ == '__main__': main()
