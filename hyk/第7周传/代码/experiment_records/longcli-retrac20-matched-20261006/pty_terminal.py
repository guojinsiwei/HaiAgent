"""PTY bridge preserves newline, cwd, exports, background jobs and Ctrl-C."""
import errno
import os
import pty
import re
import secrets
import select
import signal
import subprocess
import time
from common import ROOT,PYTHON


class PersistentTerminal:
    def __init__(self, root, cpus, logger, command_limit=300):
        self.logger,self.command_limit=logger,command_limit
        self.active_since=None
        self.marker='__RT_'+secrets.token_hex(12)+'__'
        self.master,slave=pty.openpty()
        argv=['taskset','-c',','.join(map(str,cpus)), 'setpriv','--reuid','65534','--regid','65534','--clear-groups',
            'unshare','--user','--map-root-user','--pid','--net','--fork','--kill-child=KILL',
            PYTHON,str(ROOT/'chroot_entry.py'),str(root),self.marker]
        try:
            self.process=subprocess.Popen(argv,stdin=slave,stdout=slave,stderr=slave,
                start_new_session=False,close_fds=True,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        finally: os.close(slave)
        os.set_blocking(self.master,False)
        self._carry=''

    def _read(self, wait):
        deadline=time.monotonic()+max(0.02,wait)
        chunks=[]
        while time.monotonic()<deadline:
            if self.active_since and time.monotonic()-self.active_since>=self.command_limit:
                os.write(self.master,b'\x03')
                self.active_since=None
                chunks.append(b'\n[Harness: command exceeded 300 seconds; Ctrl-C sent]\n')
                self.logger.write('command_timeout',seconds=self.command_limit)
            ready,_,_=select.select([self.master],[],[],min(0.05,max(0,deadline-time.monotonic())))
            if not ready:continue
            try:data=os.read(self.master,65536)
            except OSError as exc:
                if exc.errno==errno.EIO:break
                raise
            if not data:break
            chunks.append(data)
        text=self._carry+b''.join(chunks).decode('utf-8',errors='replace')
        # Avoid splitting a trusted prompt marker between incremental reads.
        start=text.rfind(self.marker[:5])
        if start>=0 and '\n' not in text[start:]:
            self._carry=text[start:];text=text[:start]
        else:self._carry=''
        def status(match):
            self.active_since=None
            return '[shell exit='+match.group(1)+']'
        return re.sub(re.escape(self.marker)+r'(-?\d+)\r?\n',status,text)

    def observe(self):
        return self._read(0.2)

    def execute(self, keystrokes, duration):
        if self.process.poll() is not None:
            raise RuntimeError('Isolated terminal exited')
        controls={'C-c':'\x03','C-d':'\x04','Enter':'\n','Tab':'\t'}
        keys=controls.get(keystrokes,keystrokes)
        if keys:
            if self.active_since is None:self.active_since=time.monotonic()
            raw=keys.encode('utf-8');offset=0;early=[];write_start=time.monotonic()
            while offset<len(raw):
                try:offset+=os.write(self.master,raw[offset:])
                except BlockingIOError:
                    early.append(self._read(0.02))
                    if time.monotonic()-write_start>self.command_limit:raise TimeoutError('Terminal input timeout')
        else:early=[]
        return ''.join(early)+self._read(min(duration,self.command_limit))

    def close(self):
        try: self.process.kill()
        except ProcessLookupError:pass
        self.process.wait(timeout=15)
        os.close(self.master)
