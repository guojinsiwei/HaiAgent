"""Temporary controller-only host mapping, verified HTTPS/SNI; no model calls."""
import argparse
import hashlib
import http.client
import ipaddress
from pathlib import Path
import socket
import ssl
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import save
HOST='api.deepseek.com'
TAG='# longcli-dh-raw-full20-20261004 temporary DNS repair'

def main(address):
    ipaddress.ip_address(address)
    context=ssl.create_default_context()
    connection=http.client.HTTPSConnection(HOST,443,timeout=15,context=context)
    connection._create_connection=lambda ignored,timeout,source_address=None:socket.create_connection((address,443),timeout)
    connection.request('GET','/models')
    response=connection.getresponse()
    assert response.status==401,'Unexpected unauthenticated response; no override installed'
    response.read(8192);connection.close()
    hosts=Path('/etc/hosts');original=hosts.read_text()
    matching=[line for line in original.splitlines() if HOST in line.split('#',1)[0].split()[1:]]
    if matching:
        assert all(TAG in line for line in matching),'Existing user mapping retained; manual inspection required'
        assert all(line.split()[0]==address for line in matching),'Owned mapping differs; inspect before replacement'
    else:
        backup=ROOT/'launch_tools/hosts-before.txt'
        if not backup.exists():backup.write_text(original)
        with hosts.open('a') as stream:stream.write('\n'+address+' '+HOST+' '+TAG+'\n')
    actual={a[4][0] for a in socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM)}
    assert address in actual,'Installed host mapping not visible to controller'
    save(ROOT/'launch_tools/dns-repair.json',dict(host=HOST,address=address,verified_tls=True,
        unauthenticated_http=401,model_calls=0,installed=time.time(),
        original_hosts_sha256=hashlib.sha256(original.encode()).hexdigest(),
        scope='controller container only; solver chroot still has no network',temporary=True))
    print(dict(dns_repair=True,host=HOST,address=address,tls_verified=True,model_calls=0))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--address',required=True);main(p.parse_args().address)
