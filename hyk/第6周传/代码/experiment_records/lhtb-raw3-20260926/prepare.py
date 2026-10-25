"""Bounded image preparation only: no model calls, no experiment retries."""
import json
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS = ['langchain-version-migration', 'nbody-accel-iterative', 'duckdb-optimizer-closure']

def main():
    rows = []
    for task in TASKS:
        if min(shutil.disk_usage('/var/lib/docker').free, shutil.disk_usage(HERE).free) < 60 * 2**30:
            raise RuntimeError('Less than 60 GiB free; preparation stopped without deleting data')
        image = f'zli12321/lhtb-{task}:20260615'
        # Resolve the official manifest before using a transport mirror.
        manifest = json.loads(subprocess.check_output(['docker', 'buildx', 'imagetools', 'inspect', '--raw', image], timeout=90))
        expected = next(m['digest'] for m in manifest['manifests'] if m['platform']['architecture'] == 'amd64' and m['platform']['os'] == 'linux')
        source = 'dockerproxy.net/' + image.split(':')[0] + '@' + expected
        ok = False
        for attempt in range(1, 4):
            print(json.dumps({'task': task, 'stage': 'pull', 'attempt': attempt}), flush=True)
            try:
                result = subprocess.run(['docker', 'pull', source], timeout=3600)
                ok = result.returncode == 0
            except subprocess.TimeoutExpired:
                ok = False
            if ok:
                break
            if attempt < 3:
                time.sleep(20)
        if not ok:
            raise RuntimeError(f'Image unavailable after 3 attempts: {image}')
        info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', source]))[0]
        if not any(d.endswith('@' + expected) for d in info.get('RepoDigests', [])):
            raise RuntimeError('Official image digest mismatch')
        subprocess.run(['docker', 'tag', source, image], check=True)
        rows.append({'task': task, 'image': image, 'id': info['Id'], 'size': info['Size'], 'digests': info.get('RepoDigests', [])})
        (HERE / 'images.json').write_text(json.dumps(rows, indent=2))
    print(json.dumps({'images_ready': True}), flush=True)

if __name__ == '__main__':
    main()
