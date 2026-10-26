import concurrent.futures,json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch,AsyncMock
from spending import Ledger,BudgetError
from queue_policy import AUTHORIZED,initial_rows,candidates

class RepairTests(unittest.TestCase):
 def test_no_tests_is_not_a_valid_zero_score(self):
  from verifier_setup import validate_test_report
  with tempfile.TemporaryDirectory() as d:
   v=N(trial_paths=N(verifier_dir=Path(d)))
   with self.assertRaises(FileNotFoundError):validate_test_report(v)
   Path(d,'ctrf.json').write_text(json.dumps(dict(results=dict(summary=dict(tests=0),tests=[]))))
   with self.assertRaisesRegex(RuntimeError,'did not execute'):validate_test_report(v)
   Path(d,'ctrf.json').write_text(json.dumps(dict(results=dict(summary=dict(tests=1),tests=[dict(status='failed')]))))
   validate_test_report(v)
 def test_both_harbor_identity_fields_override_only_owned_agents(self):
  import entry_harbor as h
  for name,path in [('agents:DSH',None),('agents:PureDSH',None),(None,'agents:DSH'),('agents:OfflineTimeout',None)]:
   self.assertIsNone(h.timeout(N(config=N(agent=N(name=name,import_path=path)))))
  with patch.object(h,'original',return_value=900) as old:
   self.assertEqual(h.timeout(N(config=N(agent=N(name='other',import_path=None)))),900);old.assert_called_once()
 def test_parallel_reservations_cannot_overbook_shared_total(self):
  with tempfile.TemporaryDirectory() as d:
   p=dict(campaign_limit_microcny=600000,task_limit_microcny=4000000,input_ceiling_tokens=128000,max_output_tokens=16384,requests_per_task=120,jobs=['one','two'],endpoint='fixture',model='fixture')
   ledger=Ledger(Path(d)/'cost.sqlite',p);barrier=threading.Barrier(2)
   def go(job):
    barrier.wait()
    try:ledger.reserve(dict(id=job,job=job,arm='dsh' if job=='one' else 'kz',endpoint='fixture',model='fixture',max_tokens=16384));return True
    except BudgetError:return False
   with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(go,['one','two']))
   self.assertEqual(sum(results),1);self.assertEqual(ledger.status()['reserved_microcny'],387072);self.assertGreaterEqual(ledger.status()['remaining_microcny'],0)

class VerifierSetupTests(unittest.IsolatedAsyncioTestCase):
 async def test_setup_occurs_on_verifier_and_fails_closed(self):
  import verifier_setup as v,hashlib
  with tempfile.TemporaryDirectory() as d,patch.object(v,'ROOT',Path(d)):
   blob=b'fixture';Path(d,'verifier-deps.tar.gz').write_bytes(blob)
   Path(d,'verifier-deps-provenance.json').write_text(json.dumps(dict(archive_sha256=hashlib.sha256(blob).hexdigest())))
   env=N(upload_file=AsyncMock(),exec=AsyncMock(return_value=N(return_code=1,stdout='',stderr='')))
   verifier=N(task=N(paths=N(task_dir=Path('sqlite-with-gcov'))),trial_paths=N(verifier_dir=Path(d)),environment=env,verifier_env={})
   with self.assertRaisesRegex(RuntimeError,'bootstrap failed'):await v.prepare_verifier(verifier)
   self.assertEqual(verifier.verifier_env,{})
   env.exec.return_value=N(return_code=0,stdout='',stderr='');await v.prepare_verifier(verifier)
   self.assertEqual(verifier.verifier_env['UV_DOWNLOAD_URL'],'file:///opt/kz-verifier/downloads')
   self.assertEqual(verifier.verifier_env['PIP_INDEX_URL'],verifier.verifier_env['UV_INDEX_URL'])
   self.assertNotIn('/tests/',env.exec.call_args.kwargs['command'])
if __name__=='__main__':unittest.main()
