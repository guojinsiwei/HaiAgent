"""Experiment-local egress proxy. TLS is not decrypted and contents are not logged.
Bind only the local Docker bridge. Deny proxy access to private/metadata endpoints;
task-local services are reached directly through explicit NO_PROXY entries.
"""
import http.client,ipaddress,select,socket
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit
HOST,PORT='10.123.0.1',28479
def connect(host,port):
    if port not in (80,443):raise ValueError('port not allowed')
    addresses=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):raise ValueError('non-public address')
    last=None
    for family,kind,proto,_,addr in addresses:
        s=socket.socket(family,kind,proto);s.settimeout(20)
        try:s.connect(addr);return s
        except OSError as e:last=e;s.close()
    raise last
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass
    def do_CONNECT(self):
        try:
            host,port=self.path.rsplit(':',1);up=connect(host,int(port))
        except (OSError,ValueError):self.send_error(502);return
        with up:
            self.send_response(200,'Connection Established');self.end_headers()
            while True:
                try:
                    ready,_,_=select.select((self.connection,up),[],[],600)
                    if not ready:return
                    for src in ready:
                        data=src.recv(65536)
                        if not data:return
                        (up if src is self.connection else self.connection).sendall(data)
                except OSError:return
    def do_GET(self):self.forward()
    def do_HEAD(self):self.forward()
    def forward(self):
        try:
            u=urlsplit(self.path)
            if u.scheme!='http' or not u.hostname or u.username:raise ValueError('absolute public http URL required')
            up=connect(u.hostname,u.port or 80)
            with up:
                path=(u.path or '/')+('?' +u.query if u.query else '')
                headers={k:v for k,v in self.headers.items() if k.lower() not in ('proxy-authorization','proxy-connection','connection')}
                headers['Connection']='close'
                up.sendall((self.command+' '+path+' HTTP/1.1\r\n'+''.join(k+': '+v+'\r\n' for k,v in headers.items())+'\r\n').encode('latin1'))
                while data:=up.recv(65536):self.connection.sendall(data)
        except (OSError,ValueError):self.close_connection=True
def server():return ThreadingHTTPServer((HOST,PORT),Handler)
if __name__=='__main__':server().serve_forever()
