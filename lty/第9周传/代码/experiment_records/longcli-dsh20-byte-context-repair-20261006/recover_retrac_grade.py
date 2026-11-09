"""Only finish grading the already-solved util artifact; zero model calls."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/var/tmp/lizh639-longcli-retrac20-college-20261006')
sys.path.insert(0, str(ROOT))
from common import save, sha


def main():
    health = json.loads((ROOT / 'health.json').read_text())
    assert health['state'] == 'generation_complete' and not health['active']
    job = 'retrac--61810_util'
    source = ROOT / 'jobs' / job
    summary = json.loads((source / 'summary.json').read_text())
    assert summary['state'] == 'awaiting_grade' and summary['task_processes_stopped']
    assert sha(source / 'final-source.tar.gz') == summary['artifact']['sha256']
    dest = ROOT / 'incoming' / job
    if not dest.exists():
        dest.mkdir()
        shutil.copyfile(source / 'final-source.tar.gz', dest / 'final-source.tar.gz')
        save(dest / 'summary.json', summary)
    else:
        assert sha(dest / 'final-source.tar.gz') == summary['artifact']['sha256']
    subprocess.run([sys.executable, '-B', str(ROOT / 'grade_one.py'), '--job', job, '--start'], check=True)


if __name__ == '__main__':
    main()
