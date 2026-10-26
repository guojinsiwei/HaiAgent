"""Verify public-source fidelity and freeze roundtrip acceptance artifacts."""
import json
from common import ROOT,save,sha,export_tree,assignments
from audit import verify

protocol=json.loads((ROOT/'protocol.json').read_text())
checks=[]
for worker in (0,1):
    assert json.loads((ROOT/('preflight-'+str(worker)+'.json')).read_text())['passed']
    for original in assignments(protocol,worker):
        job='worker'+str(worker)+'-v2-'+original['job']
        root=ROOT/'roots'/job/'app'
        public=ROOT/'public'/original['task']
        expected={p.relative_to(public).as_posix():sha(p) for p in public.rglob('*') if p.is_file() and not p.is_symlink()}
        actual={p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
        assert expected==actual,'Fixture modified/missed starter files: '+job
        target=ROOT/'fixtures'/job/'source-verified.tar.gz'
        artifact=export_tree(root,target,source_only=True)
        audit=verify(ROOT/'fixtures'/job/'model-audit.jsonl')
        checks.append(dict(job=job,task=original['task'],worker=worker,method=original['method'],
                           source_fidelity=True,artifact=artifact,audit=audit))
save(ROOT/'fixture-artifacts.json',dict(passed=True,checks=checks,model_calls=0))
print(json.dumps(dict(source_fidelity=True,fixtures=len(checks),model_calls=0)))
