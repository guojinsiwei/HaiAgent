"""Fresh official task checkout; never alter the previous smoke experiment."""
import hashlib,json,subprocess,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=Path('/var/tmp/lizh639-tb4-taotoken-smoke-20261011/terminal-bench')
def save(name,data):
    p=ROOT/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(data,indent=2));t.replace(p)
def main():
    selection=json.loads((ROOT/'tasks.json').read_text())
    paths=['tasks/'+r['name'] for r in selection['tasks']]
    save('prepare-status.json',dict(state='fetching_frozen_tasks',updated=time.time(),tasks=len(paths)))
    archive=ROOT/'official-tasks.tar'
    if not archive.exists():
        with archive.with_suffix('.partial').open('wb') as out:
            subprocess.run(['git','-C',str(REPO),'archive',selection['commit'],*paths],stdout=out,check=True)
        archive.with_suffix('.partial').rename(archive)
    dest=ROOT/'official'
    dest.mkdir(exist_ok=True)
    with tarfile.open(archive) as f:f.extractall(dest,filter='data')
    hashes={str(p.relative_to(dest)):hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.rglob('*') if p.is_file()}
    save('official-hashes.json',hashes)
    save('prepare-status.json',dict(state='official_sources_ready',updated=time.time(),files=len(hashes),tasks=len(paths)))
    print(json.dumps(dict(files=len(hashes),tasks=len(paths))))
if __name__=='__main__':main()
