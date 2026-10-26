"""No-inference official app provisioning, frozen instances and scoring checks."""
import json,random,time,hashlib,subprocess,faulthandler
from pathlib import Path
import numpy as np
from environments import boot_android
from instance_codec import encode,decode

r=Path('/campaign');out=Path('/output');out.mkdir(exist_ok=True)
faulthandler.dump_traceback_later(180,repeat=True)
selection=json.loads((r/'android-selection.json').read_text());emu=boot_android(out);env=None
print('CPU_EMULATOR_BOOTED',flush=True)
try:
    from android_world import registry
    from android_world.env import env_launcher
    from android_world.env.setup_device import setup,apps
    reg=registry.TaskRegistry().get_registry(registry.TaskRegistry.ANDROID_WORLD_FAMILY)
    required={apps.AndroidWorldApp,apps.ClipperApp,apps.SettingsApp};rows=[]
    for index,name in enumerate(selection['classes']):
        random.seed(selection['seed']+index);np.random.seed(selection['seed']+index)
        cls=reg[name];params=cls.generate_random_params();params.setdefault('seed',selection['seed']+index);task=cls(params)
        for app in task.app_names:
            if app:
                app_class=setup.get_app_mapping(app)
                if app_class is None:raise RuntimeError('Unknown app '+app)
                required.add(app_class)
        row={'id':'androidworld-'+name,'class':name,'params':encode(params),'instruction':task.goal,'max_steps':int(task.complexity*10),'benchmark':'androidworld'}
        assert reg[name](decode(row['params'])).goal==task.goal
        row['instance_sha256']=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest();rows.append(row)
        print('INSTANCE_FROZEN',name,flush=True)
    env=env_launcher.load_and_setup_env(adb_path='/opt/android/platform-tools/adb',emulator_setup=False)
    setup.setup_apps(env,app_list=tuple(sorted(required,key=lambda x:x.__name__)))
    print('APPS_INSTALLED',flush=True)
    checks=[]
    for row in rows:
        random.seed(row['params']['seed']);np.random.seed(row['params']['seed'])
        task=reg[row['class']](decode(row['params']));task.initialize_task(env);env.reset(go_home=True)
        state=env.get_state(wait_to_stabilize=True);assert state.pixels.size>0
        score=float(task.is_successful(env));assert score==0,(row['id'],'initial state already solves task',score)
        checks.append({'id':row['id'],'initialized':True,'official_initial_score':score,'screenshot_shape':list(state.pixels.shape),'model_calls':0})
        print('OFFICIAL_PREFLIGHT_PASSED',row['id'],flush=True)
        (r/'tasks'/str(row['id']+'.json')).write_text(json.dumps(row,indent=2))
        if hasattr(task,'tear_down'):task.tear_down(env)
    (out/'android-preflight.json').write_text(json.dumps({'passed':True,'checks':checks,'model_calls':0,'cpu_only':True},indent=2))
    print('ANDROID_PREPARATION_PASSED',flush=True)
finally:
    if env:env.close()
    subprocess.run(['adb','-s','emulator-5554','emu','kill'],timeout=20,check=False)
    try:emu.wait(timeout=30)
    except subprocess.TimeoutExpired:emu.terminate()
