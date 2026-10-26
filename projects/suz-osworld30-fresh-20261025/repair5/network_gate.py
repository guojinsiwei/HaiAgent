"""Task-scoped network repair. No answers or evaluator data enter model context."""
import json,select,socket,socketserver,threading
from pathlib import Path

SCHOLAR='36037439-2044-4b50-b9d1-875b5a332143'

class Relay(socketserver.ThreadingTCPServer):
    daemon_threads=True
    allow_reuse_address=False

class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        # The bridge listener accepts only this experiment's one CPU VM container.
        if self.client_address[0]!=self.server.allowed_peer:return
        try:
            with socket.create_connection(('127.0.0.1',28791),timeout=15) as upstream:
                for conn in (upstream,self.request):conn.settimeout(60)
                while True:
                    ready,_,_=select.select([upstream,self.request],[],[],60)
                    if not ready:return
                    for src in ready:
                        data=src.recv(65536)
                        if not data:return
                        (self.request if src is upstream else upstream).sendall(data)
        except OSError:return

def ensure_task_network(env,task,output):
    if task.get('id')!=SCHOLAR:return
    container=env.provider.container;container.reload()
    networks=container.attrs['NetworkSettings']['Networks']
    links=[n for n in networks.values() if n.get('Gateway') and n.get('IPAddress')]
    if len(links)!=1:raise RuntimeError('Scholar network gate: ambiguous container bridge')
    link=links[0]
    relay=getattr(env,'_repair5_relay',None)
    if relay:relay.shutdown();relay.server_close()
    relay=Relay((link['Gateway'],0),Handler);relay.allowed_peer=link['IPAddress']
    env._repair5_relay=relay
    threading.Thread(target=relay.serve_forever,daemon=True).start()
    host,port=relay.server_address
    code="""import subprocess,json,os
settings=[['org.gnome.system.proxy','mode','manual'],
 ['org.gnome.system.proxy','ignore-hosts',"['localhost', '127.0.0.0/8', '::1']"],
 ['org.gnome.system.proxy.http','host',HOST],['org.gnome.system.proxy.http','port',str(PORT)],
 ['org.gnome.system.proxy.https','host',HOST],['org.gnome.system.proxy.https','port',str(PORT)]]
bus='/run/user/'+str(os.getuid())+'/bus'
if os.path.exists(bus):os.environ['DBUS_SESSION_BUS_ADDRESS']='unix:path='+bus
for setting in settings:subprocess.run(['gsettings','set']+setting,check=True,capture_output=True,timeout=15)
print(json.dumps({'configured':True}))
""".replace('HOST',repr(host)).replace('PORT',str(port))
    result=env.controller.execute_python_command(code)
    try:assert json.loads(result['output'].strip())['configured']
    except (ValueError,KeyError,TypeError,AssertionError):raise RuntimeError('Scholar guest proxy setup failed') from None
    # A separate CPU Chrome profile verifies the configured system proxy without
    # touching the task's tabs, browser history or initial foreground window.
    code="""import subprocess,json,re,tempfile
profile=tempfile.mkdtemp(prefix='suz-network-preflight-')
try:
 p=subprocess.run(['google-chrome','--headless','--disable-gpu','--no-sandbox',
  '--disable-dev-shm-usage','--user-data-dir='+profile,'--dump-dom','https://scholar.google.com/'],
  capture_output=True,text=True,timeout=45)
 html=p.stdout
 print(json.dumps({'passed':p.returncode==0 and 'Google Scholar' in html and bool(re.search(r'<input[^>]+name=[\\"\\']q',html)),
  'chrome_returncode':p.returncode,'contains_search_input':bool(re.search(r'<input[^>]+name=[\\"\\']q',html)),
  'error_page':'ERR_CONNECTION' in html or 'ERR_PROXY' in html,'html_bytes':len(html)}))
except subprocess.TimeoutExpired:print(json.dumps({'passed':False,'error':'Chrome homepage timeout'}))
""".replace('\n+','\n')
    evidence={'passed':False,'cpu_only':True,'model_calls':0,'proxy':'existing local proxy via loopback SSH tunnel',
              'peer_restricted':True,'url':'https://scholar.google.com/','browser':'isolated CPU Chrome using guest system proxy'}
    try:
        result=env.controller.execute_python_command(code)
        evidence.update(json.loads(result['output'].strip()))
        if not evidence['passed']:raise RuntimeError('Scholar browser network preflight failed')
    finally:Path(output).write_text(json.dumps(evidence,indent=2))
