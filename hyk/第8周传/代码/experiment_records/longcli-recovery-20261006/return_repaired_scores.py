"""Download existing official scores only; no credentials or model calls."""
import json
from pathlib import Path
import subprocess

BASE=Path(__file__).resolve().parent
KEY='C:/Users/54177/.ssh/cubestudio_notebook'
SSH=['ssh','-i',KEY,'-o','BatchMode=yes','-o','ConnectTimeout=15','lizh639@172.16.108.236']
ROOTS=['longcli-dsh20-byte-context-repair-20261006','longcli-reflexion20-college-20261006',
       'longcli-reflexion-recovery-20261006','longcli-retrac-recovery2-20261007']


def main():
    snapshot={}
    for name in ROOTS:
        remote='/var/tmp/lizh639-'+name
        code="import json;from pathlib import Path;r=Path('"+remote+"');print(json.dumps({p.parent.name:json.loads(p.read_text()) for p in (r/'grades').glob('*/result.json')}))"
        p=subprocess.run(SSH+['/usr/bin/python3 -'],input=code,text=True,capture_output=True,check=True,timeout=45)
        reports=json.loads(p.stdout);target=BASE/'repaired-scores'/name;target.mkdir(parents=True,exist_ok=True)
        for job,report in reports.items():
            assert report['grading_state']=='complete','Never treat failed grading as zero'
            path=target/(job+'.json')
            path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        snapshot[name]={'scored':len(reports),'jobs':sorted(reports),'model_calls':0}
        print(json.dumps({'campaign':name,'returned_scores':len(reports)}),flush=True)
    (BASE/'repaired-score-return.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')


if __name__=='__main__':main()
