"""Retire only the faulty tools arm; retain every no-tools process and artifact."""
import json,os,signal,sys,time
from pathlib import Path
ROOT=Path('/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008')
sys.path.insert(0,str(ROOT))
from common import save
from runner import preserve_task
def owned(pid):
    if not isinstance(pid,int) or pid<2:return False
    p=Path('/proc',str(pid))
    try:
        if p.joinpath('stat').read_text().rsplit(')',1)[1].split()[0]=='Z':return False
        assert p.stat().st_uid==os.getuid()
        assert str(ROOT).encode() in p.joinpath('cmdline').read_bytes()
        return True
    except FileNotFoundError:return False
receipt=ROOT/'tools-retired.json'
assert not receipt.exists(),'Already retired; inspect receipt'
pid=json.loads((ROOT/'launch.json').read_text())['pid']
assert owned(pid),'Controller not alive'
os.kill(pid,signal.SIGSTOP)
time.sleep(.2)
h=json.loads((ROOT/'health.json').read_text());stopped=[];errors=[];kept=[]
try:
    # Enumerate actual children records, not only the last scheduler snapshot.
    for p in (ROOT/'jobs').glob('*/health.json'):
        s=json.loads(p.read_text());d=p.parent
        if not d.name.startswith('dh_1234_tools--'):
            if owned(s.get('pid')):kept.append({'job':d.name,'pid':s['pid']})
            continue
        if (d/'summary.json').exists():continue
        try:
            if owned(s.get('pid')):os.kill(s['pid'],signal.SIGKILL)
            preserve_task(d,s)
            s.update(stop_reason='user_requested_tools_repair',interrupted_by_user=True,ended=time.time(),updated=time.time())
            save(d/'summary.json',s);save(p,s);stopped.append(d.name)
        except Exception as e:errors.append({'job':d.name,'error':type(e).__name__})
finally:
    # Workers of the no-tools arm are independent processes and keep executing.
    if owned(pid):os.kill(pid,signal.SIGKILL)
h.update(state='running',controller_state='awaiting_no_tools_supervisor',active=[x['job'] for x in kept],
    pending=[x for x in h.get('pending',[]) if x.startswith('dh_1234_no_tools--')],updated=time.time())
save(ROOT/'health.json',h)
r={'tools_stopped':stopped,'no_tools_preserved':kept,'errors':errors,'time':time.time(),
   'no_tools_source_and_budgets_unchanged':True,'old_controller_retired':True}
save(receipt,r);print(json.dumps(r))
