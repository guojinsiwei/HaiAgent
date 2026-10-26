"""Inside a fresh isolated task container: replay previously executed file/tool actions.
No model calls, no test oracle, no invented patches. The original transcript is retained.
"""
from pathlib import Path
import json,subprocess,sys,time,hashlib
actions=json.loads(Path(sys.argv[1]).read_text());report=[]
for index,action in enumerate(actions):
    tool=action['tool'];value=action['input'];started=time.time()
    item=dict(index=index,call_id=action['callId'],tool=tool)
    try:
        if tool=='write':
            path=Path(value['file_path']);assert path.is_absolute()
            assert str(path).startswith(('/app/','/tmp/','/workspace/'))
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value['content'])
            item.update(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        elif tool=='edit':
            path=Path(value['file_path']);assert str(path).startswith(('/app/','/tmp/','/workspace/'))
            text=path.read_text();old=value['old_string'];new=value['new_string']
            count=text.count(old);assert count>0 and (value.get('replace_all') or count==1),(str(path),count)
            path.write_text(text.replace(old,new) if value.get('replace_all') else text.replace(old,new,1))
            item.update(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        elif tool=='bash':
            result=subprocess.run(['bash','-lc',value['command']],capture_output=True,text=True,timeout=120)
            item.update(returncode=result.returncode,stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),stdout_tail=result.stdout[-1200:],stderr_tail=result.stderr[-1200:])
        else:raise RuntimeError('Unsupported replay tool '+tool)
        item['state']='replayed'
    except subprocess.TimeoutExpired:
        item.update(state='bounded_timeout')
    except Exception as error:
        item.update(state='restore_error',error=str(error)[:300])
        if tool=='edit' and path.exists():item['actual_content']=path.read_text()
        report.append(item)
        print(json.dumps(dict(passed=False,actions=report)));sys.exit(2)
    item['seconds']=time.time()-started;report.append(item)
print(json.dumps(dict(passed=True,actions=report,model_calls=0)))
