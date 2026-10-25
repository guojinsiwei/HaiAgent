"""Reuse fixed official toolchain exports; import only public inputs, verify every hash."""
import json
from pathlib import Path
from common import ROOT,save,sha,import_tree

def main():
    assert not (ROOT/'ready.json').exists() and not (ROOT/'claims').exists()
    previous=Path('/mnt/lizh639/longcli-prediction-toggle10-20261003')
    target=ROOT/'templates';source=(previous/'templates').resolve(strict=True)
    if not target.exists():target.symlink_to(source,target_is_directory=True)
    assert target.resolve()==source
    manifest=json.loads((ROOT/'public-input-manifest.json').read_text())
    assert sha(ROOT/'public-inputs.tar.gz')==manifest['archive_sha256']
    if not (ROOT/'public').exists():import_tree(ROOT/'public-inputs.tar.gz',ROOT/'public')
    for name,digest in manifest['files'].items():assert sha(ROOT/name)==digest,name
    for family in ('make-pytest','c-env'):
        assert (target/family/'usr/bin/python3').is_file() and not (target/family/'tests').exists()
    save(ROOT/'reused-inputs.json',dict(templates=str(source),public_tasks=20,prior_results_used=False,
        hidden_tests_transferred=False,model_calls=0))
    print(json.dumps(dict(prepared=True,model_calls=0)))

if __name__=='__main__':main()
