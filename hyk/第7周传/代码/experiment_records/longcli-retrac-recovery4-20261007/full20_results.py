"""Trace each of 20 official scores to exactly one immutable solver artifact."""
import json
from pathlib import Path
import statistics
import time
from common import ROOT,save,sha

def build():
    plan=json.loads((ROOT/'recovery-plan.json').read_text());rows=[]
    for item in plan['reused_scored']:
        report=Path(item['report']);result=json.loads(report.read_text())
        source=Path(item['source'])/'final-source.tar.gz'
        assert result['grading_state']=='complete'
        assert sha(source)==item['artifact_sha256']==result['artifact_sha256']
        rows.append({'task':item['task'],'artifact_sha256':item['artifact_sha256'],
                     'report':str(report),'f2p':float(result['f2p']['step_score']),
                     'official_success':result.get('official_success')})
    for report in (ROOT/'grades').glob('*/result.json'):
        result=json.loads(report.read_text());task=result['task']
        assert result['grading_state']=='complete'
        source=(ROOT/'incoming'/('retrac--'+task)/'final-source.tar.gz') if task==plan['grade_only'] else (ROOT/'jobs'/('retrac--'+task)/'final-source.tar.gz')
        assert sha(source)==result['artifact_sha256']
        rows.append({'task':task,'artifact_sha256':result['artifact_sha256'],
                     'report':str(report),'f2p':float(result['f2p']['step_score']),
                     'official_success':result.get('official_success')})
    assert len(rows)==20 and len({r['task'] for r in rows})==20
    rows.sort(key=lambda r:r['task'])
    output={'state':'complete','source':'official LongCLIBench reports','tasks':rows,
            'n':20,'mean_f2p':statistics.mean(r['f2p'] for r in rows),
            'median_f2p':statistics.median(r['f2p'] for r in rows),
            'official_full_passes':sum(bool(r['official_success']) for r in rows),
            'generated_at':time.time()}
    save(ROOT/'full20-summary.json',output)
    return output

if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False))
