import json,socket,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
import runner
class Tests(unittest.TestCase):
 def test_denies_other_hosts_and_http(self):
  server=runner.ThreadingHTTPServer(('127.0.0.1',0),runner.Proxy)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   for request in [b'CONNECT github.com:443 HTTP/1.1\r\nHost: github.com\r\n\r\n',b'GET http://api.taotoken.net/ HTTP/1.1\r\nHost: api.taotoken.net\r\n\r\n']:
    with socket.create_connection(server.server_address) as client:
     client.sendall(request);self.assertIn(b'403',client.recv(1024).split(b'\r\n')[0])
  finally:server.shutdown();server.server_close()
 def test_missing_or_contradictory_scores_fail_closed(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d);(f/'verifier').mkdir()
   with patch.object(runner,'parsed_required',return_value={'a'}):
    self.assertFalse(runner.assess({},f,0)['engineering_clean'])
    (f/'verifier/output.json').write_text(json.dumps({'tests':[{'name':'a','status':'FAILED'}]}))
    (f/'verifier/reward.txt').write_text('1')
    self.assertFalse(runner.assess({},f,0)['engineering_clean'])
    (f/'verifier/reward.txt').write_text('0')
    self.assertTrue(runner.assess({},f,1)['engineering_clean'])
 def test_manifest_and_budget_agree(self):
  tasks=runner.read(runner.R/'tasks.json')['tasks'];p=runner.read(runner.R/'budget-profile.json')
  self.assertEqual(len(tasks),15);self.assertEqual(len({t['name'] for t in tasks}),15)
  self.assertEqual(len(p['jobs']),30);self.assertEqual(p['task_limit_microcny'],8000000);self.assertEqual(p['campaign_limit_microcny'],240000000)
  runner.freeze_validate()
 def test_missing_required_interface_is_valid_failure_not_infrastructure(self):
  with tempfile.TemporaryDirectory() as d:
   f=Path(d);p=f/'verifier';p.mkdir()
   (p/'output.json').write_text('{"tests":[]}');(p/'reward.txt').write_text('0')
   with patch.object(runner,'parsed_required',return_value={'TestLog'}):
    (p/'run-script-stdout.txt').write_text('network timeout\nFAIL [build failed]')
    self.assertFalse(runner.assess({},f,1)['engineering_clean'])
    (p/'run-script-stdout.txt').write_text('log/formatters_test.go:39:16: undefined: log.CRLFWriter\nFAIL pkg [build failed]')
    result=runner.assess({},f,1)
    self.assertTrue(result['engineering_clean']);self.assertEqual(result['reward'],0)
    self.assertEqual(result['failure_kind'],'compilation')
 def test_solver_mounts_do_not_expose_grader_or_answers(self):
  class S:root=runner.R/'relays/example'
  mounts=runner.install_mounts(S())
  self.assertFalse(any('tasks' in str(src) or 'upstream' in str(src) for src,_,_ in mounts))
  self.assertTrue(all(ro for _,_,ro in mounts))
if __name__=='__main__':unittest.main()
