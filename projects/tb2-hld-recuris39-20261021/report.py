"""Read live continuation status without provider/model calls."""
from pathlib import Path
import json,sqlite3
R=Path(__file__).resolve().parent
def main():
 p=R/'health.json';h=json.loads(p.read_text()) if p.exists() else {}
 out={k:h.get(k) for k in ['state','updated_utc','summary','active','spending']}
 out['pending']={a:sum(r['arm']==a and r['state']=='pending' for r in h.get('rows',[])) for a in ['hld','recuris']}
 out['issues']=[dict(task=r['task'],arm=r['arm'],result=r.get('result')) for r in h.get('rows',[]) if r['state']=='engineering_failure']
 print(json.dumps(out,indent=2))
if __name__=='__main__':main()
