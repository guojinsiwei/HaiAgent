
import json,os,signal,subprocess,sys,tempfile,time
c=json.load(sys.stdin);start=time.monotonic();timeout=False
def live_pids():
    result=set()
    for name in os.listdir('/proc'):
        if not name.isdigit():continue
        try:
            with open('/proc/'+name+'/stat') as f:state=f.read().rsplit(')',1)[1].split()[0]
            if state!='Z':result.add(int(name))
        except (OSError,IndexError):pass
    return result
before=live_pids()
with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
    try:
        p=subprocess.Popen(c['argv'],cwd=c['cwd'],stdin=subprocess.PIPE,stdout=out,stderr=err,
                           start_new_session=True,env=dict(os.environ,BASH_ENV='/dev/null',ENV='/dev/null'))
    except OSError as error:
        print(json.dumps(dict(exit_code=127 if error.errno==2 else 126,stdout='',
            stderr=str(error),timed_out=False,output_truncated=False,duration_seconds=time.monotonic()-start)))
        raise SystemExit(0)
    try:
        p.communicate((c.get('stdin') or '').encode(),timeout=c['seconds'])
    except subprocess.TimeoutExpired:
        timeout=True
    finally:
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    p.wait(timeout=3)
    # /proc here belongs ONLY to this owned task container. Stop descendants
    # that escaped the command's process group via setsid/double-fork too.
    for _ in range(20):
        extra=live_pids()-before
        if not extra:break
        for pid in extra:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
        time.sleep(.02)
    if live_pids()-before:raise RuntimeError('Command descendants did not quiesce')
    def read(f):
        n=f.tell();limit=c['output_limit'];f.seek(0)
        if n<=limit:return f.read().decode('utf-8','replace'),False
        a=f.read(limit//2);f.seek(-limit//2,2)
        return (a+b'\n[output truncated]\n'+f.read(limit//2)).decode('utf-8','replace'),True
    a,ta=read(out);b,tb=read(err)
    print(json.dumps(dict(exit_code=124 if timeout else p.returncode,stdout=a,stderr=b,
        timed_out=timeout,output_truncated=ta or tb,duration_seconds=time.monotonic()-start)))
