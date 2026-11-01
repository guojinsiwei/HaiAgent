"""Independent official grading; one bad artifact cannot stall later tasks."""
import json
import subprocess
import sys
import time
import shutil
from common import ROOT, save, sha


def main():
    handled = set(); errors = {}
    while True:
        for d in sorted((ROOT/'jobs').glob('1342--*')):
            file = d/'summary.json'
            if not file.exists() or d.name in handled:
                continue
            s = json.loads(file.read_text())
            if s.get('state') != 'awaiting_grade':
                handled.add(d.name)
                continue
            report = ROOT/'grades'/d.name/'result.json'
            if report.exists():
                handled.add(d.name)
                continue
            try:
                target = ROOT/'incoming'/d.name
                target.mkdir(exist_ok=False)
                assert sha(d/'final-source.tar.gz') == s['artifact']['sha256']
                shutil.copyfile(d/'final-source.tar.gz', target/'final-source.tar.gz')
                save(target/'summary.json', s)
                with (target/'grading.log').open('x') as out, (target/'grading-stderr.log').open('x') as err:
                    p = subprocess.run([sys.executable, '-B', str(ROOT/'grade_one.py'), '--job', d.name],
                        stdin=subprocess.DEVNULL, stdout=out, stderr=err)
                result = json.loads(report.read_text())
                assert not p.returncode and result.get('grading_state') == 'complete'
                assert result.get('grading_container_destroyed')
            except Exception as error:
                errors[d.name] = type(error).__name__
            handled.add(d.name)
        file = ROOT/'health.json'
        h = json.loads(file.read_text()) if file.exists() else {}
        terminal = h.get('state') in ('generation_complete', 'needs_attention') and not h.get('active')
        reports = [json.loads(p.read_text()) for p in (ROOT/'grades').glob('1342--*/result.json')]
        save(ROOT/'grading-health.json', dict(state='needs_attention' if errors else
            'complete_for_available_artifacts' if terminal else 'grading', updated=time.time(),
            scored=sum(r.get('grading_state') == 'complete' for r in reports), errors=errors, model_calls=0))
        if terminal:
            return
        time.sleep(5)


if __name__ == '__main__':
    main()
