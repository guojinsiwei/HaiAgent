"""Loopback-only CONNECT relay for public software registries. No TLS interception."""
import asyncio
import ipaddress
import socket
import json
import time
import urllib.request

ALLOWED = {
    "registry-1.docker.io", "auth.docker.io", "hub.docker.com",
    "production.cloudflare.docker.com", "production.cloudfront.docker.com",
    "github.com", "api.github.com", "raw.githubusercontent.com",
    "codeload.github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com",
    # Harbor's public package registry/storage; never allow telemetry hosts.
    "hlqxxzsirfrgeqasvaps.supabase.co", "ofhuhcpkvzjlejydnvyd.supabase.co",
}
SLOTS = asyncio.Semaphore(24)
DNS_CACHE = {}
DNS_LOCKS = {}
DNS_NEXT = {}

async def public_addresses(host):
    # Cube's system DNS intermittently returns unrelated addresses for Docker.
    # Resolve only allowlisted public software names over authenticated HTTPS.
    # No global DNS changes, no API credentials, no TLS interception.
    async with DNS_LOCKS.setdefault(host, asyncio.Lock()):
        cached = DNS_CACHE.get(host)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        def resolve():
            # Global resolver selected a very slow overseas CloudFront edge.
            # AliDNS selects a nearer official edge; TLS still authenticates
            # the original hostname end-to-end and no content is substituted.
            endpoint = 'https://dns.alidns.com/resolve' if host == 'production.cloudfront.docker.com' else 'https://8.8.8.8/resolve'
            with urllib.request.urlopen(endpoint+'?name='+host+'&type=A&edns_client_subnet=0.0.0.0/0', timeout=15) as response:
                body = json.load(response)
            if body.get('Status') != 0:
                raise socket.gaierror('DNS query failed')
            answers = [item for item in body.get('Answer',[]) if item.get('type') == 1 and ipaddress.ip_address(item['data']).is_global]
            if not answers:
                raise socket.gaierror('No public A records')
            return min(300, max(1, min(item.get('TTL',30) for item in answers))), [item['data'] for item in answers]
        ttl, addresses = await asyncio.to_thread(resolve)
        DNS_CACHE[host] = (time.monotonic()+ttl, addresses)
        return addresses

def allowed(host):
    return host in ALLOWED or (host.startswith("docker-images-prod.") and host.endswith(".r2.cloudflarestorage.com"))

async def pipe(reader, writer, activity, small_first_write=False):
    first = True
    while True:
        if first and small_first_write:
            # A client's record header and body may arrive in separate reads.
            # Buffer one bounded record so the complete first record uses the
            # same small writes (Docker's Go TLS client differs from curl).
            head = await asyncio.wait_for(reader.readexactly(5), timeout=15)
            length = int.from_bytes(head[3:5], 'big')
            if head[0] != 22 or not 0 < length <= 32768:
                raise ValueError('Expected bounded initial TLS handshake record')
            data = head + await asyncio.wait_for(reader.readexactly(length),timeout=15)
        else:
            # A large download legitimately has no client-to-server bytes for
            # minutes. Idle timeout must cover the CONNECTION, not each direction.
            data = await reader.read(65536)
        if not data:
            return
        activity[0] = time.monotonic()
        if first and small_first_write:
            # Preserve every TLS byte end-to-end; bound the initial write size
            # for this network path. No certificates/HTTP contents are changed.
            for offset in range(0,len(data),64):
                writer.write(data[offset:offset+64])
                await writer.drain()
                await asyncio.sleep(0.01)
        else:
            writer.write(data)
            await writer.drain()
        first = False

async def idle_watchdog(activity):
    while True:
        await asyncio.sleep(30)
        if time.monotonic() - activity[0] > 180:
            raise asyncio.TimeoutError('Connection idle in both directions')

async def handle(reader, writer):
    upstream = None
    jobs = []
    async with SLOTS:
        try:
            header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=10)
            method, destination, version = header.split(b"\r\n", 1)[0].decode("ascii").split()
            host, port = destination.rsplit(":", 1)
            host = host.lower()
            if method != "CONNECT" or port != "443" or not allowed(host):
                print("DENIED", method[:12], host[:160], port[:8], flush=True)
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            for attempt in range(3):
                try:
                    addresses = await public_addresses(host)
                    break
                except (socket.gaierror, asyncio.TimeoutError):
                    if attempt == 2:
                        raise
                    await asyncio.sleep(attempt + 1)
            public = [item for item in addresses if ipaddress.ip_address(item).is_global]
            if not public:
                raise ValueError("No public destination")
            offset = DNS_NEXT.get(host,0) % len(public)
            DNS_NEXT[host] = offset+1
            public = public[offset:]+public[:offset]
            # Connect to the address checked above, without a second DNS resolution.
            # Prefer IPv4, try a bounded number of checked public addresses.
            for index, address in enumerate(public[:3]):
                try:
                    source, upstream = await asyncio.wait_for(asyncio.open_connection(address, 443), timeout=10)
                    break
                except (OSError, asyncio.TimeoutError):
                    if index == min(len(public), 3) - 1:
                        raise
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            activity = [time.monotonic()]
            jobs = [asyncio.create_task(pipe(reader, upstream, activity, small_first_write=True)),
                    asyncio.create_task(pipe(source, writer, activity)),
                    asyncio.create_task(idle_watchdog(activity))]
            done, pending = await asyncio.wait(jobs, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except Exception as exc:
            print("CONNECTION_END", locals().get('host','unknown'), type(exc).__name__, flush=True)
        finally:
            for task in jobs:
                task.cancel()
            if jobs:
                await asyncio.gather(*jobs, return_exceptions=True)
            if upstream:
                upstream.close()
            writer.close()

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", 28761, limit=8192)
    print("RELAY_READY loopback:28761 TLS passthrough; public software allowlist", flush=True)
    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())
