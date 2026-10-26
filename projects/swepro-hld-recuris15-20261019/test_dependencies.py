import io,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import dependencies as dep

class DependencyCache(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
  self.root=patch.object(dep,'R',root);self.cache=patch.object(dep,'CACHE',root/'dependency-cache/go')
  self.root.start();self.cache.start();dep.CACHE.mkdir(parents=True)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),dep.Handler)
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.url=f'http://127.0.0.1:{self.server.server_port}'
 def tearDown(self):
  self.server.shutdown();self.server.server_close();self.cache.stop();self.root.stop();self.tmp.cleanup()
 def test_preserves_artifact_bytes_and_serves_subsequent_request_without_network(self):
  # Keep the client opener separate from the mocked upstream opener.
  opener=urllib.request.build_opener()
  with patch.object(dep.urllib.request,'urlopen',return_value=io.BytesIO(b'public-module-zip')) as upstream:
   for _ in range(2):
    with opener.open(self.url+'/example.org/module/@v/v1.0.0.zip') as r:self.assertEqual(r.read(),b'public-module-zip')
   self.assertEqual(upstream.call_count,1)
   self.assertEqual(upstream.call_args.args[0],'https://proxy.golang.org/example.org/module/@v/v1.0.0.zip')
 def test_signed_sumdb_records_use_mirror_and_unrelated_paths_are_denied(self):
  opener=urllib.request.build_opener()
  with patch.object(dep.urllib.request,'urlopen',return_value=io.BytesIO(b'signed-checksum-record')) as upstream:
   with opener.open(self.url+'/sumdb/sum.golang.org/lookup/example.org/module@v1.0.0') as r:self.assertEqual(r.status,200)
   self.assertTrue(upstream.call_args.args[0].startswith('https://goproxy.cn/sumdb/sum.golang.org/'))
   for route in ['/etc/passwd','/example.org/../secret/@v/v1.zip','/example.org/%2e%2e/secret/@v/v1.zip']:
    with self.assertRaises(urllib.error.HTTPError) as error:opener.open(self.url+route)
    self.assertEqual(error.exception.code,400)
   self.assertEqual(upstream.call_count,1)
 def test_missing_module_is_not_cached_as_success(self):
  opener=urllib.request.build_opener();route='/example.org/missing/@v/v1.0.0.zip'
  with patch.object(dep.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('upstream',404,'missing',{},None)):
   with self.assertRaises(urllib.error.HTTPError) as error:opener.open(self.url+route)
   self.assertEqual(error.exception.code,404)
   self.assertFalse(dep.artifact_path(route).exists())
 def test_go_uppercase_escape_maps_to_standard_module_cache_path(self):
  opener=urllib.request.build_opener()
  with patch.object(dep.urllib.request,'urlopen',return_value=io.BytesIO(b'{"Version":"v0.3.1"}')):
   with opener.open(self.url+'/github.com/%21burnt%21sushi/toml/@v/v0.3.1.info') as r:self.assertEqual(r.status,200)
   self.assertTrue((dep.CACHE/'github.com/!burnt!sushi/toml/@v/v0.3.1.info').is_file())

if __name__=='__main__':unittest.main()
