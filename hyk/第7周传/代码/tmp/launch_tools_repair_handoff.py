"""Fresh secret in anonymous pipes; resume no-tools and wait for new tools acceptance."""
import json,os,subprocess,sys,time
from pathlib import Path
OLD=Path('/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008')
NEW=Path('/mnt/sdb/home/lizh639/longcli-dh-tools-output-repair2-20261008')
OPS=Path('/mnt/sdb/home/lizh639/dh-tools-output-repair2-ops')
def child(script,key,log):
    with (OPS/(log+'.log')).open('x') as out,(OPS/(log+'-stderr.log')).open('x') as err:
        p=subprocess.Popen([sys.executable,'-B',str(script)],stdin=subprocess.PIPE,stdout=out,stderr=err,
                           start_new_session=True,text=True)
        p.stdin.write(key+'\n');p.stdin.close()
    return p
def main():
    key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
    if '--worker' in sys.argv:
        resumed=child(OPS/'resume_no_tools_supervisor.py',key,'no-tools-supervisor')
        (OPS/'status.json').write_text(json.dumps({'state':'no_tools_resumed_waiting_tools_acceptance','pid':os.getpid(),'no_tools_pid':resumed.pid}))
        for _ in range(1440):
            if (NEW/'ready.json').exists() and (OPS/'release-tools.json').exists():
                p=child(NEW/'launch.py',key,'tools-launch');p.wait()
                (OPS/'status.json').write_text(json.dumps({'state':'tools_launch_returned','returncode':p.returncode,'no_tools_pid':resumed.pid}))
                return
            time.sleep(5)
        raise RuntimeError('tools_acceptance_wait_expired')
    os.close(os.open(OPS/'handoff.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    with (OPS/'handoff.log').open('x') as out,(OPS/'handoff-stderr.log').open('x') as err:
        p=subprocess.Popen([sys.executable,'-B',__file__,'--worker'],stdin=subprocess.PIPE,
                           stdout=out,stderr=err,start_new_session=True,text=True)
        p.stdin.write(key+'\n');p.stdin.close()
    print(json.dumps({'handoff_started':True,'pid':p.pid,'new_tools_require_sealed_acceptance':True}))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'error_type':type(e).__name__}));raise SystemExit(1)
