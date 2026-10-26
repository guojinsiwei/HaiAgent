"""Score the attested pre-verifier snapshot, with zero model calls."""
from pathlib import Path
import hashlib,json,subprocess,time,uuid
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'tb2-hld-v9-failed8-20261022'
TRIAL=next((OLD/'jobs/tb2v9a8-01-hld-v9-crack-7z-hash').glob('*/submission-snapshot.json')).parent
OUT=ROOT/'tb2-score-recovery-v2'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args,**kw):return subprocess.run(args,check=True,capture_output=True,text=True,**kw)
def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2))

def main():
    OUT.mkdir(exist_ok=False)
    snapshot=json.loads((TRIAL/'submission-snapshot.json').read_text())
    task=Path(json.loads((TRIAL/'config.json').read_text())['task']['path'])
    cache=OLD/'dependency-cache/crack-7z-hash';spec=json.loads((cache/'ready.json').read_text())
    assert sha(task/'tests/test.sh')==spec['test_sha256']
    assert sha(cache/'dependencies.tar')==spec['archive_sha256']
    cached=json.loads((ROOT/'curl-dependency-ready.json').read_text())
    assert cached['source_snapshot']==snapshot['image_id']
    image=cached['image'];name='hld-score-recovery-'+uuid.uuid4().hex[:12]
    run(['docker','image','inspect',image])
    (OUT/'verifier').mkdir()
    run(['docker','create','--name',name,'--label','experiment='+ROOT.name,'--network','none','--cpus','2','--memory','8g',
         '--mount',f'type=bind,src={task}/tests,dst=/tests,readonly',
         '--mount',f'type=bind,src={OUT}/verifier,dst=/logs/verifier','-w','/app',image,'sleep','infinity'])
    try:
        run(['docker','start',name]);run(['docker','cp',str(cache/'dependencies.tar'),name+':/tmp/recovery-deps.tar'])
        prep=r'''set -eu
test -x /usr/bin/curl
/usr/bin/curl --version >/dev/null
tar -xf /tmp/recovery-deps.tar -C /opt
mkdir -p /opt/kz-verifier/shims /root/.local/bin
cp /opt/kz-verifier/bin/uv /opt/kz-verifier/bin/uvx /root/.local/bin/
cat > /root/.local/bin/env <<'EOF'
export PATH=/opt/kz-verifier/shims:/root/.local/bin:$PATH
EOF
cat > /opt/kz-verifier/shims/apt-get <<'EOF'
#!/bin/sh
set -eu
case "$*" in
 'update'|'install -y curl') test -x /usr/bin/curl; /usr/bin/curl --version >/dev/null; exit 0;;
 *) echo 'Uncached apt request rejected' >&2; exit 90;;
esac
EOF
cat > /opt/kz-verifier/shims/curl <<'EOF'
#!/bin/sh
case "$*" in
 '-LsSf https://astral.sh/uv/0.9.5/install.sh') echo 'test -x /root/.local/bin/uv'; exit 0;;
 *) exec /usr/bin/curl "$@";;
esac
EOF
chmod 755 /opt/kz-verifier/shims/apt-get /opt/kz-verifier/shims/curl
'''
        run(['docker','exec',name,'bash','-c',prep],timeout=180)
        env=['-e','PATH=/opt/kz-verifier/shims:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
             '-e','UV_CACHE_DIR=/opt/kz-verifier/cache','-e','UV_PYTHON_INSTALL_DIR=/opt/kz-verifier/python',
             '-e','UV_OFFLINE=true','-e','UV_PYTHON_DOWNLOADS=never','-e','UV_LINK_MODE=copy',
             '-e','UV_INDEX_URL='+spec.get('dependency_index','https://pypi.org/simple')]
        proof=run(['docker','exec',*env,name,'/root/.local/bin/uvx','--offline',*spec['args'][1:]],timeout=120)
        save('preflight.json',dict(passed=True,paid_model_calls=0,network='none',image=image,official_test_sha256=spec['test_sha256'],dependency_archive_sha256=spec['archive_sha256'],resolution=proof.stdout.strip()))
        started=time.time()
        with (OUT/'verifier/test-stdout.txt').open('w') as log:
            p=subprocess.run(['docker','exec',*env,name,'bash','/tests/test.sh'],stdout=log,stderr=log,timeout=600)
        report=json.loads((OUT/'verifier/ctrf.json').read_text());summary=report['results']['summary']
        assert summary['tests']>0 and len(report['results']['tests'])==summary['tests']
        reward=float((OUT/'verifier/reward.txt').read_text().strip());assert reward in (0,1)
        save('result.json',dict(task='crack-7z-hash',reward=reward,engineering_clean=True,model_calls=0,
             source_trial=str(TRIAL),snapshot=snapshot,test_summary=summary,grader_returncode=p.returncode,seconds=time.time()-started,historical_result_preserved=True))
        print((OUT/'result.json').read_text())
    finally:
        run(['docker','rm','-f',name])

if __name__=='__main__':main()
