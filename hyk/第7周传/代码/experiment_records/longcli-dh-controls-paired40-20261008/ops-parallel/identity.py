"""Owned PID identities. Never inspect credentials, environment or process memory."""
import os
from pathlib import Path


def process_status(pid,root,expected_start=None,proc_root=Path('/proc'),uid=None):
    if type(pid) is not int or pid<2:return {'status':'exited'}
    p=proc_root/str(pid)
    try:
        fields=(p/'stat').read_text().rsplit(')',1)[1].split()
        if fields[0] in ('Z','X'):return {'status':'exited','start':fields[19]}
        start=fields[19]
        if expected_start is not None and str(expected_start)!=start:return {'status':'reused','start':start}
        if p.stat().st_uid!=(os.getuid() if uid is None else uid):return {'status':'foreign','start':start}
        cmd=(p/'cmdline').read_bytes()
        if not cmd:return {'status':'unknown','start':start,'reason':'empty_live_cmdline'}
        if str(root).encode() not in cmd:return {'status':'foreign','start':start}
        final=(p/'stat').read_text().rsplit(')',1)[1].split()
        if final[0] in ('Z','X'):return {'status':'exited','start':start}
        if final[19]!=start:return {'status':'reused','start':final[19]}
        return {'status':'running','start':start,'process_state':final[0]}
    except FileNotFoundError:return {'status':'exited'}
    except (OSError,IndexError,ValueError) as error:return {'status':'unknown','reason':type(error).__name__}


class AdoptedProcess:
    exitcode=None
    def __init__(self,pid,start,root):self.pid=pid;self.start=start;self.root=root
    def is_alive(self):
        state=process_status(self.pid,self.root,self.start)
        if state['status']=='unknown':raise RuntimeError('uncertain_owned_process_state')
        return state['status']=='running'
    def join(self,*args):pass
    def kill(self):
        import signal
        state=process_status(self.pid,self.root,self.start)
        if state['status']=='unknown':raise RuntimeError('uncertain_owned_process_state')
        if state['status']=='running':os.kill(self.pid,signal.SIGKILL)
