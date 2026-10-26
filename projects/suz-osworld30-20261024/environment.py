"""CPU-only OSWorld VM wrapper; official setup and evaluators remain unchanged."""
from pathlib import Path
import os
import sys

ROOT=Path(__file__).resolve().parent
os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['NVIDIA_VISIBLE_DEVICES']='void'
os.environ['OSWORLD_RECORDING_UPDATE']='off'
sys.path.insert(0,str(ROOT/'OSWorld'))


def make_environment():
    from filelock import FileLock
    import desktop_env.providers.docker.provider as provider_module
    from desktop_env.providers.docker.provider import DockerProvider
    # Other users may also allocate ports. Keep the shared upstream lock; wait
    # rather than deleting/bypassing it. Serialize this experiment's VM starts.
    provider_module.LOCK_TIMEOUT=300
    if not getattr(DockerProvider,'_suz_start_serialized',False):
        original_start=DockerProvider.start_emulator
        def start_serialized(self,*args,**kwargs):
            with FileLock(str(ROOT/'cpu-vm-start.lock'),timeout=600):
                return original_start(self,*args,**kwargs)
        DockerProvider.start_emulator=start_serialized
        DockerProvider._suz_start_serialized=True
    if not getattr(DockerProvider,'_suz_cpu_only',False):
        original= DockerProvider._create_container
        def create_cpu(self,**kwargs):
            devices=kwargs.get('devices',[])
            if any('nvidia' in str(device).lower() or '/dev/dri' in str(device).lower() for device in devices):
                raise RuntimeError('GPU devices forbidden')
            kwargs.update(runtime='runc',nano_cpus=4_000_000_000,mem_limit='6g',
                          labels={'experiment':'suz-osworld30-20261024','owner':'lizh639'})
            kwargs['environment']={**kwargs.get('environment',{}),'NVIDIA_VISIBLE_DEVICES':'void','CUDA_VISIBLE_DEVICES':''}
            kwargs['ports']={key:('127.0.0.1',value) for key,value in kwargs.get('ports',{}).items()}
            return original(self,**kwargs)
        DockerProvider._create_container=create_cpu
        DockerProvider._suz_cpu_only=True
    from desktop_env.desktop_env import DesktopEnv
    images=list((ROOT/'vm').rglob('Ubuntu.qcow2'))
    if len(images)!=1:raise RuntimeError('Expected one verified official VM image')
    return DesktopEnv(provider_name='docker',path_to_vm=str(images[0]),action_space='pyautogui',
        require_a11y_tree=False,require_terminal=False,headless=True,recording_update='off',
        cache_dir=str(ROOT/'assets'),screen_size=(1920,1080))
