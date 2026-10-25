import os,subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
kz=ROOT/'runtime/kz';node=ROOT/'runtime/node/bin/node'
env=dict(os.environ,PATH=str(node.parent)+':'+os.environ.get('PATH',''))
tests=sorted(str(p.relative_to(kz)) for p in (kz/'tests').glob('*.test.mjs'))+['tests/deep-audit.mjs','tests/migration-round2.mjs','tests/migration-round3.mjs']
with (ROOT/'regressions-full.tap').open('w') as out:r=subprocess.run([str(node),'--test','--test-reporter=tap',*tests],cwd=kz,env=env,stdout=out,stderr=subprocess.STDOUT)
print('\n'.join((ROOT/'regressions-full.tap').read_text().splitlines()[-10:]));raise SystemExit(r.returncode)
