import socket
import time
import concurrent.futures
def one(ip):
    start=time.monotonic()
    try:
        with socket.create_connection((ip,443),timeout=8): pass
        return ip,round(time.monotonic()-start,3)
    except OSError as e: return ip,type(e).__name__
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    print(list(pool.map(one,['13.35.190.54','13.249.231.103','13.35.36.33'])))
