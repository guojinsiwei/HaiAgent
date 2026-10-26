import argparse
from datetime import datetime, timezone, timedelta
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchmark_runtime import atomic_write_json, canonical_sha256
from benchmark_splits import frozen_swebench_ids
import prepare_swe_comparison as launch
from swe_batch import load_plan


def task(identity):
    return {'instance_id':identity,'repo':'django/django','base_commit':'a'*40,'version':'4.1',
            'problem_statement':'public issue', 'recipe':{'cached_environment_yml':'dependencies:\n - python=3.9\n'}}


def plan(tasks):
    data={'schema_version':1,'count':len(tasks),'dataset':'test','split':'test','tasks':tasks,
          'excluded_ids':[],'sample_seed':123}
    data['plan_sha256']=canonical_sha256(data)
    return data


class ComparisonPreparationTests(unittest.TestCase):
    def test_stable_replacement_order_and_unchanged_originals(self):
        a,b,c,d=map(task,['a__a-1','b__b-1','c__c-1','d__d-1'])
        before=plan([a,b])
        final,changes=launch.choose_tasks(before,plan([c,d]),{a['instance_id']:'ready'},
                                           {d['instance_id']:'ready',c['instance_id']:'ready'})
        self.assertEqual(final,[a,c])
        self.assertEqual(changes[0]['removed'],b['instance_id'])
        self.assertEqual(before['tasks'],[a,b])

    def test_never_shrink_denominator(self):
        with self.assertRaises(ValueError):
            launch.choose_tasks(plan([task('a__a-1')]),plan([task('b__b-1')]),{}, {})

    def test_all_originals_ready_needs_no_reserve(self):
        a=task('a__a-1')
        result,changes=launch.choose_tasks(plan([a]),plan([task('b__b-1')]),{a['instance_id']:'ready'},{})
        self.assertEqual(result,[a]);self.assertEqual(changes,[])

    def test_preparing_state_not_counted_as_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=task('a__a-1')
            atomic_write_json(root/'states/a__a-1.json',{'status':'preparing'})
            atomic_write_json(root/'prepared/a__a-1/ready.json',{})
            (root/'prepared/a__a-1/pip-freeze.txt').write_text('')
            self.assertEqual(launch.available(root,plan([a])),{})

    def test_real_reserves_exclude_originals_and_frozen_tests(self):
        original=load_plan(launch.ROOT/'examples/swe100-plan.json')
        reserve=load_plan(launch.ROOT/'examples/swe100-reserve-plan.json')
        ids={t['instance_id'] for t in reserve['tasks']}
        self.assertEqual(len(ids),40)
        self.assertFalse(ids & {t['instance_id'] for t in original['tasks']})
        self.assertFalse(ids & set(frozen_swebench_ids()))
        self.assertFalse(ids & set(original['excluded_ids']))

    def test_expired_deadline_stops_before_preparation_or_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            with patch.object(launch,'prepare_task') as prepare,patch.object(launch.run_comparison,'main') as paid:
                with self.assertRaisesRegex(ValueError,'Deadline reached'):
                    launch.main(['--source-root',str(base/'old'),'--reserve-plan','unused',
                                 '--root',str(base/'new'),'--output-root',str(base/'out'),
                                 '--deadline','2020-01-01T00:00:00+00:00','--start-comparison'])
                prepare.assert_not_called();paid.assert_not_called()

    def test_freeze_preserves_old_metadata_and_records_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);old=base/'old';new=base/'new'
            a,b,c=map(task,['a__a-1','b__b-1','c__c-1'])
            original,reserve=plan([a,b]),plan([c])
            for root,t in [(old,a),(new,c)]:
                identity=t['instance_id']
                atomic_write_json(root/'states'/(identity+'.json'),{'id':identity,'status':'prepared'})
                atomic_write_json(root/'prepared'/identity/'ready.json',{'id':identity,'recipe_sha256':canonical_sha256(t),
                                  'base_commit':t['base_commit'],'goal':t['problem_statement'],'workspace':'existing-seed'})
                (root/'prepared'/identity/'pip-freeze.txt').write_text('package==1\n')
            atomic_write_json(old/'states/b__b-1.json',{'id':'b__b-1','status':'prepare_error','error':'dependency error'})
            before=(old/'states/b__b-1.json').read_bytes()
            args=argparse.Namespace(root=new,source_root=old)
            result,frozen=launch.freeze(args,original,reserve)
            self.assertEqual([t['instance_id'] for t in result['tasks']],['a__a-1','c__c-1'])
            self.assertEqual(before,(old/'states/b__b-1.json').read_bytes())
            self.assertEqual(launch.freeze(args,original,reserve)[0],result)
            self.assertEqual(load_plan(frozen/'task-plan.json')['plan_sha256'],result['plan_sha256'])
            audit=json.loads((frozen/'replacement-audit.json').read_text())
            self.assertEqual(audit[0]['source_preparation_state']['error'],'dependency error')


if __name__=='__main__':
    unittest.main()
