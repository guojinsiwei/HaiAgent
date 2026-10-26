"""No-model positive/negative official scoring check in a disposable CPU VM."""
import io
import json
from PIL import Image
from environment import ROOT,make_environment

directory=ROOT/'preflight-gui';directory.mkdir(exist_ok=True)
task=json.loads((ROOT/'tasks/os/a4d98375-215b-4a4d-aee9-3d4370fccc41.json').read_text())
env=None
try:
    env=make_environment()
    obs=env.reset(task_config=task)
    (directory/'initial.png').write_bytes(obs['screenshot'])
    with Image.open(io.BytesIO(obs['screenshot'])) as image:
        assert image.width>=1000 and image.height>=700
    env.provider.container.reload()
    host=env.provider.container.attrs['HostConfig']
    assert host.get('Runtime')=='runc' and not host.get('DeviceRequests')
    assert all('nvidia' not in str(d).lower() and '/dev/dri' not in str(d).lower() for d in host.get('Devices',[]))
    initial=env.evaluate()
    assert initial==0,('Expected known negative score',initial)
    setup=env.setup_controller.setup([{'type':'execute','parameters':{'command':[
        'gsettings','set','org.gnome.desktop.screensaver','lock-enabled','true']}}],False)
    assert setup is not False
    positive=env.evaluate()
    assert positive==1,('Expected known positive score',positive)
    env.is_environment_used=True
    env.reset(task_config=task)
    restored=env.evaluate()
    assert restored==0,('Fresh reset failed',restored)
    obs,_,_,_=env.step('pyautogui.moveTo(400, 300)',pause=1)
    assert obs['screenshot']
    result={'cpu_only':True,'screenshot':True,'gui_action':True,'negative_score':initial,
            'positive_score':positive,'fresh_reset_score':restored,'model_calls':0}
    (directory/'result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
    (ROOT/'logs/gui.ready').write_text('passed\n')
finally:
    if env is not None:env.close()
