import json,sqlite3,tempfile,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
import runner,resume_remaining
class Tests(unittest.TestCase):
 def test_paid_job_or_saved_work_cannot_be_admitted(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d)
   with sqlite3.connect(r/'spending.sqlite') as db:db.execute('create table calls (job text)')
   with patch.object(resume_remaining,'R',r):
    resume_remaining.verify_admission({'index':8})
    with sqlite3.connect(r/'spending.sqlite') as db:db.execute("insert into calls values ('swp-08-hld')")
    with self.assertRaisesRegex(RuntimeError,'repeated paid'):resume_remaining.verify_admission({'index':8})
    (r/'jobs/swp-10-recuris').mkdir(parents=True)
    with self.assertRaisesRegex(RuntimeError,'repeated paid'):resume_remaining.verify_admission({'index':10})
 def test_teleport_exception_requires_exact_instance_and_both_controls(self):
  task=runner.read(runner.R/'tasks.json')['tasks'][7]
  folder=runner.R/'preflight'/task['name']
  empty=runner.read(folder/'empty/result.json');gold=runner.read(folder/'gold/result.json')
  self.assertTrue(runner.validate_preflight(task,folder,empty,gold))
  self.assertFalse(runner.validate_preflight(task,folder,empty,{**gold,'reward':0}))
  self.assertFalse(runner.validate_preflight({**task,'name':'another-task'},folder,empty,gold))
 def test_pull_retries_are_bounded_and_leave_audit_logs(self):
  with tempfile.TemporaryDirectory() as d,patch.object(runner,'R',Path(d)),patch.object(runner.time,'sleep') as sleep:
   with patch.object(runner.subprocess,'run',return_value=subprocess.CompletedProcess([],1)),patch.object(runner,'run',side_effect=[subprocess.CalledProcessError(1,['docker','pull']),None]) as call,patch.object(runner,'output',return_value=b'[{"Id":"sha256:fixture","RepoDigests":[]}]'):
    task={'name':'fixture','image':'fixture:1'};folder=runner.image_prepare(task)
    self.assertEqual(call.call_count,2);self.assertEqual(task['image_id'],'sha256:fixture');self.assertEqual(len(list(folder.glob('pull-repair-*.log'))),2)
   with patch.object(runner.subprocess,'run',return_value=subprocess.CompletedProcess([],1)),patch.object(runner,'run',side_effect=subprocess.CalledProcessError(1,['docker','pull'])) as call:
    with self.assertRaises(subprocess.CalledProcessError):runner.image_prepare({'name':'failed','image':'fixture:2'})
    self.assertEqual(call.call_count,4)
if __name__=='__main__':unittest.main()
