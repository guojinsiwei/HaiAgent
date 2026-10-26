"""Verify declared GUI launches are mapped before the first agent observation."""
from pathlib import Path
import json,shlex,time

FAMILIES={'libreoffice':['libreoffice','soffice'],'soffice':['libreoffice','soffice'],
    'google-chrome':['google-chrome','chromium'],'google-chrome-stable':['google-chrome','chromium'],
    'chromium':['chromium','google-chrome'],'vlc':['vlc'],'gimp':['gimp'],'code':['code']}
QUERY="""import subprocess,json,re
rows=[]
for line in subprocess.check_output(['wmctrl','-lx'],text=True).splitlines():
 parts=line.split(None,4)
 if len(parts)<4:continue
 detail=subprocess.run(['xwininfo','-id',parts[0]],capture_output=True,text=True).stdout
 width=re.search(r'Width: (\\d+)',detail);height=re.search(r'Height: (\\d+)',detail)
 kind=subprocess.run(['xprop','-id',parts[0],'_NET_WM_WINDOW_TYPE'],capture_output=True,text=True).stdout
 if ('Map State: IsViewable' in detail and width and height and int(width[1])>=160 and int(height[1])>=90
     and not any(x in kind for x in ['SPLASH','DOCK','DESKTOP'])):
  rows.append({'id':parts[0],'class':parts[2],'width':int(width[1]),'height':int(height[1])})
print(json.dumps(rows))
"""

def required_windows(task):
    result=[]
    for action in task.get('config',[]):
        if action.get('type')!='launch':continue
        command=action.get('parameters',{}).get('command',[])
        if isinstance(command,str):command=shlex.split(command)
        if not command:continue
        name=Path(command[0]).name
        if name in FAMILIES and FAMILIES[name] not in result:result.append(FAMILIES[name])
    return result

def windows_ready(windows,required):
    return all(any(any(name in row.get('class','').lower() for name in group) for row in windows) for group in required)

def wait_desktop_ready(env,task,output,timeout=60):
    required=required_windows(task);started=time.monotonic();windows=[]
    previous=None
    if required:
        while True:
            response=env.controller.execute_python_command(QUERY)
            try:windows=json.loads(response['output'].strip())
            except (TypeError,KeyError,ValueError):windows=[]
            identities=sorted(row['id'] for row in windows)
            if windows_ready(windows,required) and identities==previous:break
            previous=identities
            if time.monotonic()-started>=timeout:
                raise RuntimeError('Declared GUI application window not ready before inference')
            time.sleep(2)
    # Let the compositor paint the mapped application before screenshot capture.
    time.sleep(2)
    Path(output).write_text(json.dumps({'required_window_families':required,'mapped_windows':windows,
        'elapsed_seconds':time.monotonic()-started,'passed':True,'model_visible':False},indent=2))

