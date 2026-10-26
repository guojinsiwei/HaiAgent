import json,tempfile,unittest
from pathlib import Path
from status import normalized

class RetryStatus(unittest.TestCase):
 def test_newer_explicit_retry_replaces_archived_fault_without_counting_a_pass(self):
  with tempfile.TemporaryDirectory() as d:
   old=dict(task='same',arm='recuris',state='engineering_failed',started=10)
   retry=dict(task='same',arm='recuris',state='running',started=20,repair='literal_memory_context')
   Path(d,'literal-retry-health.json').write_text(json.dumps(dict(original_ledger=True,rows={'swp-08-recuris':retry})))
   h=normalized(d,dict(rows={'swp-08-recuris':old}))
   self.assertEqual(h['rows']['swp-08-recuris']['state'],'running')
   self.assertEqual(h['summary']['recuris'],dict(completed=0,passed=0,engineering_failed=0))
   self.assertEqual(old['state'],'engineering_failed')
 def test_retry_cannot_overwrite_another_task_or_completed_result(self):
  with tempfile.TemporaryDirectory() as d:
   retry=dict(task='same',arm='recuris',state='running',started=20,repair='literal_memory_context')
   Path(d,'literal-retry-health.json').write_text(json.dumps(dict(original_ledger=True,rows={'swp-08-recuris':retry})))
   for row in [dict(task='different',arm='recuris',state='engineering_failed',started=10),dict(task='same',arm='recuris',state='completed',reward=1,started=10)]:
    h=normalized(d,dict(rows={'swp-08-recuris':row}))
    self.assertEqual(h['rows']['swp-08-recuris']['state'],row['state'])

if __name__=='__main__':unittest.main()
