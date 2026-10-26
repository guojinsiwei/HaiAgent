"""Private rootfs entry with a model-only Unix bridge; no external task network.

The host proxy holds the real key. This process receives only a random per-job
proxy token. A task cannot reach host files, hidden tests or other task roots.
"""
import ctypes
import encodings.idna
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import resource
import socket
import struct
import subprocess
import sys
import threading

from device_setup import validate_devices


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    spec = json.loads(sys.argv[2])
    assert root != Path('/') and (root / 'usr/bin/python3').is_file()
    validate_devices(root)
    # Only loopback is enabled inside an otherwise empty network namespace.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        flags = struct.unpack('16sh', fcntl.ioctl(sock, 0x8913, struct.pack('16sh', b'lo', 0))[:18])[1]
        fcntl.ioctl(sock, 0x8914, struct.pack('16sh', b'lo', flags | 1))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    for limit, value in ((resource.RLIMIT_NOFILE, 256), (resource.RLIMIT_NPROC, 128),
                         (resource.RLIMIT_AS, 3 * 2**30), (resource.RLIMIT_CORE, 0),
                         (resource.RLIMIT_FSIZE, 256 * 2**20)):
        resource.setrlimit(limit, (value, value))
    os.chroot(root)
    os.chdir('/app')
    libc = ctypes.CDLL(None, use_errno=True)
    for cap in range(41):
        if libc.prctl(24, cap, 0, 0, 0) and ctypes.get_errno() != 22:
            raise OSError(ctypes.get_errno(), 'capability bounding drop')
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]
    header, data = Header(0x20080522, 0), (Data * 2)()
    if libc.capset(ctypes.byref(header), data) or libc.prctl(38, 1, 0, 0, 0):
        raise OSError(ctypes.get_errno(), 'privilege drop')

    class Bridge(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            size = int(self.headers.get('Content-Length', '0'))
            if self.path != '/v1/chat/completions' or not 0 < size <= 32 * 2**20:
                self.send_error(403)
                return
            payload = self.rfile.read(size)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
                upstream.settimeout(95)
                upstream.connect('/dsh-relay/proxy.sock')
                request = (f'POST /v1/chat/completions HTTP/1.0\r\nHost: localhost\r\nContent-Type: application/json\r\n'
                           f'Authorization: {self.headers.get("Authorization", "")}\r\nContent-Length: {size}\r\n\r\n').encode()
                upstream.sendall(request + payload)
                # Forward the complete HTTP response, including SSE frames.
                while True:
                    chunk = upstream.recv(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                self.close_connection = True

    server = ThreadingHTTPServer(('127.0.0.1', 0), Bridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {'PATH': '/opt/dsh/node/package/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': '/tmp', 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'OMP_NUM_THREADS': '2', 'OPENBLAS_NUM_THREADS': '2',
           'DSH_HOME': '/dsh-home', 'DSH_TELEMETRY_DISABLED': '1', 'DSH_PERMISSION_MODE': 'danger-full-access',
           'DSH_APPROVAL_POLICY': 'never', 'LONGCLI_PROXY_URL': f'http://127.0.0.1:{server.server_port}/v1',
           'LONGCLI_PROXY_TOKEN': spec['proxy_token']}
    try:
        result = subprocess.run(spec['argv'], env=env, close_fds=True)
        raise SystemExit(result.returncode)
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
