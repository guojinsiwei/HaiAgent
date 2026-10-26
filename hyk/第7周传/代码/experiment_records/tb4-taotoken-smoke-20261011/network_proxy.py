"""Campaign-local CONNECT proxy: only TaoToken and official Python package hosts.
Bound to the Docker bridge gateway, never to the campus/public interface.
TLS remains end-to-end; no request/response contents or credentials are logged.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import select
import socket
import subprocess
import sys
import threading

ALLOWED = {'api.taotoken.net', 'pypi.org', 'files.pythonhosted.org'}
ROOT = Path(__file__).resolve().parent
HOST, PORT = '10.123.0.1', 28476

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_CONNECT(self):
        if self.path not in {name+':443' for name in ALLOWED}:
            self.send_error(403)
            return
        try:
            upstream = socket.create_connection((self.path[:-4], 443), timeout=20)
        except OSError:
            self.send_error(502)
            return
        with upstream:
            self.send_response(200, 'Connection Established')
            self.end_headers()
            peers=(self.connection, upstream)
            while True:
                ready, _, _ = select.select(peers, [], [], 600)
                if not ready:
                    return
                for src in ready:
                    data=src.recv(65536)
                    if not data:
                        return
                    (upstream if src is self.connection else self.connection).sendall(data)

if '--serve' in sys.argv:
    server=ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Timer(14400, server.shutdown).start()
    server.serve_forever()
else:
    with (ROOT/'network-proxy.log').open('ab', buffering=0) as log:
        p=subprocess.Popen([sys.executable, __file__, '--serve'], stdin=subprocess.DEVNULL,
            stdout=log,stderr=log,start_new_session=True)
    (ROOT/'network-proxy.pid').write_text(str(p.pid))
    print(json.dumps({'pid':p.pid,'bind':HOST,'port':PORT,'allowed':sorted(ALLOWED)}))
