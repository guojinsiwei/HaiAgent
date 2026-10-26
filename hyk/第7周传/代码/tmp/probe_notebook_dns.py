import concurrent.futures
import json
import os
import subprocess
import sys
import time

def probe(option):
    env = dict(os.environ)
    if option == 'ndots1':
        env['RES_OPTIONS'] = 'ndots:1'
    started = time.monotonic()
    try:
        result = subprocess.run([sys.executable, '-c', "import socket; assert socket.getaddrinfo('api.deepseek.com',443)"],
                                env=env, capture_output=True, timeout=18)
        return {'mode': option, 'ok': result.returncode == 0, 'seconds': round(time.monotonic()-started, 3)}
    except subprocess.TimeoutExpired:
        return {'mode': option, 'ok': False, 'seconds': 18}

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    rows = list(pool.map(probe, ['default', 'ndots1'] * 3))
print(json.dumps({'host': os.uname().nodename, 'samples': rows}))
