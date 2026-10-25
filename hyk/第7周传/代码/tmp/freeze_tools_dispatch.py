"""Stop admission, NOT solving children, for an explicitly requested fleet handoff."""
import json,os,signal,time
from pathlib import Path
root=Path('/var/tmp/longcli-dh-tools-execution-repair3-20261008')
h=json.loads((root/'health.json').read_text());pid=h['pid'];proc=Path('/proc')/str(pid)
assert proc.stat().st_uid==os.getuid()
assert str(root).encode() in (proc/'cmdline').read_bytes()
assert h['state']=='running'
os.kill(pid,signal.SIGSTOP)
time.sleep(2)
started={p.name for p in (root/'jobs').iterdir() if p.is_dir()}
p=json.loads((root/'protocol.json').read_text())
pending=[r for r in p['tasks'] if 'dh_tools--'+r['task'] not in started]
receipt={'original_controller_pid':pid,'time':time.time(),'state':'admission_paused_children_continue',
 'started_jobs':sorted(started),'pending_tasks':[r['task'] for r in pending],'child_tasks_not_interrupted':True}
(root/'fleet-handoff.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt))
