"""Model-only CONNECT with bounded DNS/address recovery and explicit diagnostics."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json,socket,select,time,threading,ssl

def connect(host,port,timeout=6):
    errors=[]
    # Try IPv4 first; do not spend the whole timeout on an unreachable IPv6 route.
    for family in [socket.AF_INET,socket.AF_INET6]:
        try:addresses=socket.getaddrinfo(host,port,family,socket.SOCK_STREAM)
        except OSError as e:errors.append(type(e).__name__);continue
        for af,kind,proto,_,address in addresses[:3]:
            stream=socket.socket(af,kind,proto);stream.settimeout(timeout)
            try:stream.connect(address);stream.settimeout(None);return stream
            except OSError as e:errors.append(type(e).__name__);stream.close()
    raise OSError('model_upstream_unreachable:'+','.join(errors))

def connectivity_check():
    with connect('api.taotoken.net',443) as raw:
        raw.settimeout(10)
        with ssl.create_default_context().wrap_socket(raw,server_hostname='api.taotoken.net') as stream:
            # No authorization or model inference. Verify TLS AND HTTP routing.
            stream.sendall(b'HEAD /token/v1/messages HTTP/1.1\r\nHost: api.taotoken.net\r\nConnection: close\r\n\r\n')
            first=stream.recv(8192).split(b'\r\n',1)[0].decode('ascii','replace')
            status=int(first.split()[1])
            if status>=500 or status in (408,429):raise OSError('model_http_unavailable:'+str(status))
            return dict(tls=stream.version(),http_status=status)

def server(host,circuit,log_path):
    lock=threading.Lock()
    def record(event):
        with lock:
            with open(log_path,'a') as f:f.write(json.dumps(dict(time=time.time(),**event))+'\n')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_CONNECT(self):
            if self.path!='api.taotoken.net:443':self.send_error(403);return
            try:up=connect('api.taotoken.net',443)
            except OSError as e:
                record(dict(event='connect_failed',error=str(e)));circuit.fail('model_proxy_connect_failed')
                try:self.send_error(502)
                except OSError:pass
                return
            with up:
                self.send_response(200);self.end_headers()
                try:
                    while True:
                        ready,_,_=select.select((self.connection,up),[],[],420)
                        if not ready:return
                        for source in ready:
                            data=source.recv(65536)
                            if not data:return
                            (up if source is self.connection else self.connection).sendall(data)
                except OSError:return
    result=ThreadingHTTPServer((host,0),Handler);result.daemon_threads=True
    threading.Thread(target=result.serve_forever,daemon=True).start()
    return result
