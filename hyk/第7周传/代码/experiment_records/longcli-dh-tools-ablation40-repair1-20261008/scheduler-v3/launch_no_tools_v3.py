import json,os,subprocess,sys,time,hashlib
from pathlib import Path
ROOT=Path('/mnt/sdb/home/lizh639/longcli-dh-tools-ablation40-repair1-20261008')
OPS=Path(__file__).resolve().parent
def main():
 ready=json.loads((OPS/'acceptance.json').read_text());assert ready['passed']
 for name,digest in ready['hashes'].items():assert hashlib.sha256((OPS/name).read_bytes()).hexdigest()==digest
 sys.path.insert(0,str(ROOT))
 from common import validate,save
 validate();assert (ROOT/'supervisor-v3-preparation.json').exists()
 assert not (OPS/'launch.claim').exists()
 if '--check' in sys.argv:print(json.dumps({'ready':True,'concurrency':6,'source_unchanged':True}));return
 key=sys.stdin.readline().strip();assert key and not any(c.isspace() for c in key)
 import urllib.request
 class NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self,*args):return None
 req=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+key})
 with urllib.request.build_opener(NoRedirect()).open(req,timeout=30) as response:listing=json.load(response)
 assert any(x['id']=='deepseek-flash' for x in listing['data'])
 os.close(os.open(OPS/'launch.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
 from no_tools_supervisor_v3 import process_status
 health=json.loads((ROOT/'health.json').read_text())
 health.update(state='starting',controller_state='v3_starting',updated=time.time(),pid=os.getpid())
 save(ROOT/'health.json',health)
 old_grader=json.loads((ROOT/'grading-launch.json').read_text())
 state=process_status(old_grader.get('pid'))['status']
 if state in ('exited','foreign','reused'):
  save(OPS/'previous-grading-launch.json',old_grader)
  with (OPS/'grading-worker.log').open('x') as out,(OPS/'grading-stderr.log').open('x') as err:
   grader=subprocess.Popen([sys.executable,'-B',str(ROOT/'grading_worker.py')],stdin=subprocess.DEVNULL,
       stdout=out,stderr=err,start_new_session=True)
  save(ROOT/'grading-launch.json',{'pid':grader.pid,'model_calls':0,'time':time.time()})
 elif state!='running':raise RuntimeError('Grader identity uncertain')
 with (OPS/'worker.log').open('x') as out,(OPS/'worker-stderr.log').open('x') as err:
  p=subprocess.Popen([sys.executable,'-B',str(OPS/'no_tools_supervisor_v3.py'),str(ROOT)],
    stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True,text=True)
  p.stdin.write(key+'\n');p.stdin.close()
 save(OPS/'launch.json',{'pid':p.pid,'time':time.time(),'key_storage':'RAM only'})
 print(json.dumps({'started':True,'pid':p.pid,'scope':'8 pending + 3 interrupted retries; cow adopted if still alive'}))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'error_type':type(e).__name__}));raise SystemExit(1)
