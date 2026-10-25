"""Prepare/seal a new campaign; reuse only immutable public and official inputs."""
import argparse
import json
from pathlib import Path
from common import ROOT,save,sha

def main(kind):
    p=json.loads((ROOT/'protocol.json').read_text())
    assert p['methods']==['dh'] and len(p['tasks'])==p['total_trials']==10
    assert p['expectation_enabled'] and not p['route_search'] and not p['contrastive_predictions']
    assert not (ROOT/'claims').exists() and not list(ROOT.glob('health-*.json'))
    if kind=='solver':
        old=Path('/mnt/lizh639/longcli-dh-raw-full20-20261004')
        for folder in ('templates','public'):
            (ROOT/folder).symlink_to((old/folder).resolve(strict=True),target_is_directory=True)
        manifest=json.loads((old/'public-input-manifest.json').read_text())
        for name,digest in manifest['files'].items():
            if name.split('/')[1] in {r['task'] for r in p['tasks']}:
                assert sha(ROOT/name)==digest,name
        save(ROOT/'public-input-manifest.json',dict(reused_public_only=True,
            prior_results_carried=0,hidden_tests_transferred=False))
        print(json.dumps(dict(prepared=True,model_calls=0)))
    elif kind=='college':
        old=Path('/var/tmp/lizh639-longcli-dh-raw-full20-20261004')
        (ROOT/'upstream').symlink_to(old/'upstream',target_is_directory=True)
        (ROOT/'input-manifest.json').write_bytes((old/'input-manifest.json').read_bytes())
        manifest=json.loads((ROOT/'input-manifest.json').read_text())
        files=[ROOT/n for n in manifest['files']]
        assert all(sha(f)==manifest['files'][f.relative_to(ROOT).as_posix()] for f in files)
        files += [ROOT/n for n in ('college_grader.py','common.py','protocol.json','input-manifest.json')]
        save(ROOT/'college-ready.json',dict(ready=True,hashes={f.relative_to(ROOT).as_posix():sha(f) for f in files},model_calls=0))
        print(json.dumps(dict(ready=True,model_calls=0)))
    elif kind=='seal':
        for worker in (0,1):
            report=json.loads((ROOT/f'preflight-{worker}.json').read_text())
            assert report['passed'] and report['model_calls']==0 and len(report['checks'])==5
        files=list(ROOT.glob('*.py'))+list(ROOT.glob('*.json'))
        for folder in ('sources','compatibility'):
            files += [f for f in (ROOT/folder).rglob('*') if f.is_file() and '__pycache__' not in f.parts]
        files += [f for row in p['tasks'] for f in (ROOT/'public'/row['task']).rglob('*') if f.is_file()]
        save(ROOT/'ready.json',dict(ready=True,hashes={f.relative_to(ROOT).as_posix():sha(f) for f in files},
            methods=['dh'],tasks=10,trials=10,generation_concurrency=4,model_calls=0))
        print(json.dumps(dict(ready=True,trials=10,model_calls=0)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=('solver','college','seal'))
    main(parser.parse_args().kind)
