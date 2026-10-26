"""Bounded cold-boot readiness before official task initialization."""
import json,subprocess,time
from pathlib import Path

def wait_ready(process,directory):
    adb=['adb','-s','emulator-5554']
    def run(*args,timeout=15):
        return subprocess.run(adb+list(args),capture_output=True,text=True,timeout=timeout,check=True).stdout.strip()
    history=[]
    for attempt in range(4):
        try:
            if process.poll() is not None:raise RuntimeError('CPU emulator exited during readiness')
            run('wait-for-device',timeout=30)
            # adbd restarts when changing to root. Complete that transition before
            # AndroidWorld's initializer issues its own root/file/setup requests.
            run('root');run('wait-for-device',timeout=30)
            stable=0
            for _ in range(15):
                if process.poll() is not None:raise RuntimeError('CPU emulator exited during readiness')
                ready=(run('get-state')=='device' and run('shell','getprop','sys.boot_completed')=='1'
                       and run('shell','id','-u')=='0'
                       and run('shell','service','check','package')=='Service package: found')
                stable=stable+1 if ready else 0
                if stable>=3:
                    Path(directory,'adb-readiness.json').write_text(json.dumps({'passed':True,'attempt':attempt+1,
                        'stable_samples':stable,'root_ready':True,'model_calls':0,'prior_failures':history},indent=2))
                    return
                time.sleep(2)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired,RuntimeError) as exc:
            history.append(type(exc).__name__)
        if process.poll() is not None:break
        time.sleep(2)
    raise RuntimeError('ADB did not become stably ready after four bounded cold-boot checks')
