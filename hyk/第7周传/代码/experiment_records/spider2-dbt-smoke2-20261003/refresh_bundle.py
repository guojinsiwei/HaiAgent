"""Preserve the initial bundle and package the qualified shm repair."""
import json
import tarfile
from common import ROOT,save,sha
from spider_grader import validate_inputs


def main():
    validate_inputs()
    original=ROOT/'solver-inputs.tar.gz'
    original.rename(ROOT/'solver-inputs-before-shm.tar.gz')
    protocol=json.loads((ROOT/'protocol.json').read_text())
    files=list(ROOT.glob('*.py'))+[ROOT/'protocol.json',ROOT/'data-provenance.json',ROOT/'README.md']
    folders=[ROOT/'sources',ROOT/'compatibility']+[ROOT/'public'/r['task'] for r in protocol['tasks']]
    files += [p for folder in folders for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    with tarfile.open(original,'x:gz') as archive:
        for p in files:archive.add(p,arcname=p.relative_to(ROOT).as_posix(),recursive=False)
    result=dict(archive_sha256=sha(original),files={p.relative_to(ROOT).as_posix():sha(p) for p in files},
                contains_gold=False,shared_memory_repair=True,model_calls=0)
    save(ROOT/'solver-input-manifest.json',result)
    print(json.dumps(dict(updated=True,archive_sha256=result['archive_sha256'],model_calls=0)),flush=True)


if __name__=='__main__':main()
