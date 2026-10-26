"""Bounded DNS cache/fallback with original HTTPS host, SNI and certificate checks.
No provider error bodies, headers, credentials or response contents in diagnostics.
"""
import http.client
import json
import multiprocessing
import socket
import ssl
import time
import urllib.parse

CACHE={}

def connect_addresses(addresses,port,until):
    last=None
    for family,address in addresses:
        remaining=until-time.monotonic()
        if remaining<=0: raise TimeoutError('deadline')
        sock=socket.socket(family,socket.SOCK_STREAM)
        sock.settimeout(min(10,remaining))
        try:
            sock.connect((address,port))
            sock.settimeout(max(.1,until-time.monotonic()))
            return sock
        except OSError as error:
            last=error; sock.close()
    raise last or OSError('No addresses')

def worker(send,endpoint,payload,key,seconds,cached,cached_at):
    until=time.monotonic()+seconds
    phase='dns'; addresses=[]; refreshed=None
    meta={}
    try:
        url=urllib.parse.urlsplit(endpoint)
        if url.scheme!='https' or url.hostname!='api.deepseek.com' or url.port not in (None,443):
            raise ValueError('Unapproved transport endpoint')
        age=time.time()-cached_at
        if cached and age<300:
            addresses=cached; meta['dns_source']='cache_fresh'
        else:
            try:
                addresses=list(dict.fromkeys((af,addr[0]) for af,_,_,_,addr in socket.getaddrinfo(url.hostname,443,type=socket.SOCK_STREAM)))
                refreshed=time.time(); meta['dns_source']='resolved'
            except socket.gaierror as error:
                meta['dns_error_errno']=error.errno
                if not cached or age>1800: raise
                addresses=cached; meta['dns_source']='cache_on_dns_failure'
        phase='connect_tls'
        connection=http.client.HTTPSConnection(url.hostname,443,timeout=max(.1,until-time.monotonic()),context=ssl.create_default_context())
        connection._create_connection=lambda address,timeout,source_address=None: connect_addresses(addresses,443,until)
        # HTTPSConnection.connect wraps this socket with server_hostname=url.hostname.
        connection.connect()
        phase='request_response'
        connection.request('POST' if payload is not None else 'GET',url.path or '/',
            body=json.dumps(payload).encode() if payload is not None else None,
            headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        response=connection.getresponse()
        body=response.read(2_000_001)
        status=response.status
        connection.close()
        result=('ok',body) if status==200 and len(body)<=2_000_000 else ('http',status) if status!=200 else ('error','response_too_large')
        send.send((result,addresses,refreshed,meta))
    except Exception as error:
        cause=error.__cause__ or error
        meta.update(phase=phase,error_type=type(error).__name__,errno=getattr(cause,'errno',None))
        kind='fatal' if isinstance(error,(ssl.SSLError,ValueError)) else 'error'
        send.send(((kind,type(error).__name__),addresses,refreshed,meta))
    finally:
        send.close()

def request(endpoint,payload,key,seconds,recorder=None):
    host=urllib.parse.urlsplit(endpoint).hostname
    cached,cached_at=CACHE.get(host,([],0))
    ctx=multiprocessing.get_context('spawn')
    receiver,sender=ctx.Pipe(duplex=False)
    process=ctx.Process(target=worker,args=(sender,endpoint,payload,key,seconds,cached,cached_at),daemon=True)
    until=time.monotonic()+seconds
    process.start(); sender.close()
    try:
        if not receiver.poll(max(0,until-time.monotonic())):
            result=('error','absolute_request_timeout'); meta={'phase':'absolute_deadline'}
        else:
            try:
                result,addresses,refreshed,meta=receiver.recv()
            except EOFError:
                result=('error','transport_worker_exited'); meta={'phase':'worker_exit'}
            else:
                if refreshed and addresses: CACHE[host]=(addresses,refreshed)
                if result[0]=='error' and meta.get('phase')=='connect_tls': CACHE.pop(host,None)
        if recorder: recorder.emit('transport_diagnostic',**meta)
        return result
    finally:
        receiver.close()
        if process.is_alive(): process.terminate()
        process.join(.5)
        if process.is_alive(): process.kill(); process.join(.5)
