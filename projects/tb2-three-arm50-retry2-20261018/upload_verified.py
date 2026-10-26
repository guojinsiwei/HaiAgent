"""Attest trusted deployment bytes at the host/container boundary."""
import hashlib,shlex
from pathlib import Path
async def upload_verified(env,source,target):
 source=Path(source)
 if source.is_symlink() or not source.is_file():raise RuntimeError('Deployment archive must be a regular file: '+source.name)
 if target not in ('/installed-agent/runtime.tar.gz','/installed-agent/python-runtime.tar.gz','/installed-agent/native-runtime.tar.gz','/tmp/kz-verifier-deps.tar.gz'):
  raise RuntimeError('Unexpected deployment destination')
 digest=hashlib.sha256(source.read_bytes()).hexdigest()
 await env.upload_file(source,target)
 q=shlex.quote(target)
 command=f"set -eu; test ! -L {q}; test -f {q}; chmod 0644 {q}; printf '%s  %s\\n' {shlex.quote(digest)} {q} | sha256sum -c -"
 result=await env.exec(command=command,user='root',timeout_sec=120)
 if result.return_code:raise RuntimeError('Deployment archive verification failed: '+source.name)
