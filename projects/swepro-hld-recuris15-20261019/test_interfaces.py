import copy,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import runner,resume_interfaces

class Tests(unittest.TestCase):
 def controls(self):
  for t in runner.read(runner.R/'tasks.json')['tasks']:
   if t['index'] in (14,15):
    f=runner.R/'preflight'/t['name']
    yield t,f,runner.read(f/'dependency-empty/result.json'),runner.read(f/'dependency-gold/result.json')
 def test_actual_controls_and_preserved_results(self):
  for t,f,e,g in self.controls():
   old=(f/'dependency-empty/result.json').read_bytes()
   self.assertTrue(runner.validate_preflight(t,f,e,g),t['name'])
   self.assertEqual((f/'dependency-empty/result.json').read_bytes(),old)
   scored=runner.assess(t,f/'dependency-empty',1)
   self.assertTrue(scored['engineering_clean'])
   self.assertEqual(scored['reward'],0)
   self.assertEqual(scored['failure_kind'],'required_interface_missing')
 def test_reject_unproven_or_unrelated_failure(self):
  for t,f,e,g in self.controls():
   self.assertFalse(runner.validate_preflight(t,f,e,{**g,'reward':0}))
   self.assertFalse(runner.validate_preflight(t,f,e,{**g,'required_passed':0}))
   self.assertFalse(runner.validate_preflight(t,f,{**e,'exit_code':124},g))
   self.assertFalse(runner.validate_preflight({**t,'name':'unrelated'},f,e,g))
   raw='\n'.join(p.read_text() for p in (f/'dependency-empty/verifier').glob('run-script-*.txt'))
   self.assertTrue(runner.required_interface_failure(t,raw))
   for extra in ['\nModuleNotFoundError: requests','\ni/o timeout','\nno space left on device']:
    self.assertFalse(runner.required_interface_failure(t,raw+extra))
   self.assertFalse(runner.required_interface_failure(t,raw.replace('FlagKey','UnknownField').replace('ALLOWED_COVER_HOSTS','UNKNOWN_CONSTANT')))
   self.assertFalse(runner.assess(t,f/'dependency-empty',124)['engineering_clean'])
 def test_only_unstarted_four_jobs_can_launch(self):
  self.assertEqual(resume_interfaces.INDICES,[14,15])
  with tempfile.TemporaryDirectory() as d,patch.object(resume_interfaces,'R',Path(d)):
   r=Path(d)
   with sqlite3.connect(r/'spending.sqlite') as db:db.execute('create table calls(job text)')
   resume_interfaces.unpaid({'index':14})
   with sqlite3.connect(r/'spending.sqlite') as db:db.execute("insert into calls values('swp-14-hld')")
   with self.assertRaisesRegex(RuntimeError,'repeated paid'):resume_interfaces.unpaid({'index':14})
   (r/'jobs/swp-15-recuris').mkdir(parents=True)
   with self.assertRaisesRegex(RuntimeError,'repeated paid'):resume_interfaces.unpaid({'index':15})

if __name__=='__main__':unittest.main()
