"""No-model renderer and official-controller diagnostic, preserving each phase."""
import io,json,subprocess,time,traceback
from pathlib import Path
from PIL import Image
from environments import boot_android
out=Path('/output');out.mkdir(exist_ok=True);emu=boot_android(out);env=None
def adb_screen(label):
    p=subprocess.run(['adb','exec-out','screencap','-p'],capture_output=True,timeout=30)
    (out/(label+'.png')).write_bytes(p.stdout)
    print(label,'return',p.returncode,'bytes',len(p.stdout),'stderr',p.stderr.decode(errors='replace')[:200],flush=True)
try:
    adb_screen('before-controller')
    from android_world.env import env_launcher
    env=env_launcher.load_and_setup_env(adb_path='/opt/android/platform-tools/adb',emulator_setup=False)
    print('CONTROLLER_READY',flush=True);adb_screen('after-controller')
    state=env.get_state(wait_to_stabilize=True)
    Image.fromarray(state.pixels).save(out/'official-observation.png')
    print('OFFICIAL_SCREEN',state.pixels.shape,flush=True)
    (out/'passed.json').write_text(json.dumps({'passed':True,'model_calls':0}))
except Exception:traceback.print_exc();raise
finally:
    p=subprocess.run(['adb','shell','logcat','-d','-t','1000'],capture_output=True,timeout=30)
    (out/'android-logcat.txt').write_bytes(p.stdout)
    if env:env.close()
    subprocess.run(['adb','emu','kill'],timeout=20,check=False)
