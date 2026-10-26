import tempfile,unittest,types
from pathlib import Path
from unittest.mock import AsyncMock
from upload_verified import upload_verified
class Tests(unittest.IsolatedAsyncioTestCase):
 async def test_symlink_fails_before_transfer(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder);(p/'real').write_bytes(b'archive');(p/'link').symlink_to(p/'real')
   env=types.SimpleNamespace(upload_file=AsyncMock(),exec=AsyncMock())
   with self.assertRaisesRegex(RuntimeError,'regular file'):await upload_verified(env,p/'link','/installed-agent/runtime.tar.gz')
   env.upload_file.assert_not_called()
 async def test_mismatched_or_unreadable_container_copy_fails(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'real';p.write_bytes(b'archive')
   env=types.SimpleNamespace(upload_file=AsyncMock(),exec=AsyncMock(return_value=types.SimpleNamespace(return_code=1)))
   with self.assertRaisesRegex(RuntimeError,'verification failed'):await upload_verified(env,p,'/installed-agent/runtime.tar.gz')
   self.assertIn('sha256sum -c',env.exec.call_args.kwargs['command'])
 async def test_success_requires_container_attestation(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'real';p.write_bytes(b'archive')
   env=types.SimpleNamespace(upload_file=AsyncMock(),exec=AsyncMock(return_value=types.SimpleNamespace(return_code=0)))
   await upload_verified(env,p,'/installed-agent/runtime.tar.gz')
   env.upload_file.assert_awaited_once();env.exec.assert_awaited_once()
if __name__=='__main__':unittest.main()
