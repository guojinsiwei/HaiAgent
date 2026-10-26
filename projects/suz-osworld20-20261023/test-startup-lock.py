"""No VM/inference calls: concurrent boot serialization regression."""
import concurrent.futures,hashlib,json,threading,time
from environment import ROOT,make_environment
import desktop_env.providers.docker.provider as provider
import desktop_env.desktop_env as desktop
active=0;peak=0;mutex=threading.Lock()
def fake_start(*args,**kwargs):
    global active,peak
    with mutex:active+=1;peak=max(peak,active)
    time.sleep(.15)
    with mutex:active-=1
    return True
provider.DockerProvider.start_emulator=fake_start
desktop.DesktopEnv=lambda **kw:provider.DockerProvider.start_emulator(object.__new__(provider.DockerProvider))
assert make_environment() is True
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(lambda _:make_environment(),range(4)))
assert all(results) and peak==1 and provider.LOCK_TIMEOUT==300
result={'passed':True,'concurrent_boot_peak':peak,'waiting_seconds':provider.LOCK_TIMEOUT,'model_calls':0,
        'environment_sha256':hashlib.sha256((ROOT/'environment.py').read_bytes()).hexdigest()}
(ROOT/'logs/startup-lock-test.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
