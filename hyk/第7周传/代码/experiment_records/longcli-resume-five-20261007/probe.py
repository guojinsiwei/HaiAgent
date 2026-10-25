import json
from pathlib import Path
base=Path('/mnt/sdb/home/lizh639')
names=['longcli-lats-taco-small20-20261007','longcli-recuris-frozen-small20-20261007','longcli-dh-large20-20261007','longcli-retrac-recovery4-20261007']
for name in names:
    root=base/name
    print('CAMPAIGN',name)
    print('ENTRIES',[(p.name,'dir' if p.is_dir() else 'file') for p in root.iterdir() if p.is_dir() or p.name in ('protocol.json','college_grader.py')])
    h=json.loads((root/'health.json').read_text())
    print('HEALTH',{k:h.get(k) for k in ('state','pid','errors')})
    for pat in ('jobs/taco--61810_util','jobs/recuris_frozen--cs61_fa24_ants','jobs/dh--cs61_fa24_cats','jobs/retrac--61810_net'):
        d=root/pat
        if not d.exists():continue
        for fname in ('summary.json','recuris-result.json'):
            f=d/fname
            if f.exists():
                obj=json.loads(f.read_text());print(fname,{k:obj.get(k) for k in ('state','engineering_fault','error','stop_reason','error_frames')})
        for sub in ('model','api'):
            files=sorted((d/sub).glob('response-*.json'))[-2:]
            for f in files:
                obj=json.loads(f.read_text());c=obj.get('choices',[{}])[0]
                content=c.get('message',{}).get('content','')
                print(f.name,{'finish':c.get('finish_reason'),'chars':len(content),'head':content[:250],'tail':content[-500:]})
        f=d/'trace/events.jsonl'
        if f.exists():
            rows=[json.loads(s) for s in f.read_text().splitlines()]
            print('EVENT_ERRORS',[r for r in rows if 'error' in r.get('event','') or 'invalid' in r.get('event','')][-5:])
        f=d/'model-audit.jsonl'
        if f.exists():
            rows=[json.loads(s) for s in f.read_text().splitlines()]
            print('DH_LAST_ERRORS',[r for r in rows if r.get('event') in ('wire_rejected','model_error')][-8:])
            for r in [r for r in rows if r.get('event')=='wire_response' and r.get('envelope')][-2:]:
                c=r['envelope']['choices'][0];content=c['message'].get('content','')
                print('DH_RESPONSE',{'finish':c.get('finish_reason'),'chars':len(content),'head':content[:300],'tail':content[-600:]})
