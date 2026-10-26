"""Fixtures for stale PIDs, recovery counts, partition merges and offline state."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import json
from monitor import summarize, reconcile, update_state
import remote_probe as probe


def task(name, state, updated=10, node='college', score=None):
    return {'task': name, 'job': 'taco--'+name, 'state': state, 'updated': updated,
            'node': node, 'score': score, 'official_success': score == 1}


def campaign(node, root, tasks, created=100, cohort='same-source', expected=20):
    return {'id': node+'|'+root+'|taco', 'node': node, 'root': root, 'method': 'taco',
        'created': created, 'cohort': cohort, 'tasks': tasks, 'expected': expected,
        'controller_alive': any(t['state']=='running' for t in tasks),
        'grader_alive': True, 'raw_state': 'running', 'observed_at': 100, 'errors': []}


class ProgressTests(unittest.TestCase):
    def test_tool_campaign_is_visible_even_when_not_running(self):
        c=campaign('college','tool-root',[task('a','pending')],expected=1)
        c['method']='dh_tools'
        c['id']='college|tool-root|dh_tools'
        rows=reconcile({'college':{'ok':True,'data':{'campaigns':[c]}}})
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['method'],'dh_tools')

    def test_shared_stop_is_interruption_not_independent_task_fault(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path);(root/'jobs/dh_tools--a').mkdir(parents=True)
            (root/'protocol.json').write_text(json.dumps({'methods':['dh_tools'],'tasks':[{'task':'a'}]}))
            (root/'jobs/dh_tools--a/summary.json').write_text(json.dumps({
                'state':'interrupted','engineering_fault':'shared_stop_RuntimeError'}))
            c=probe.collect_root(root,'college',time.time())[0]
            self.assertEqual(c['tasks'][0]['state'],'interrupted')

    def test_dead_running_label_is_not_reported_as_alive(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path);(root/'jobs/taco--a').mkdir(parents=True)
            (root/'protocol.json').write_text(json.dumps({'methods':['taco'],'tasks':[{'task':'a'}]}))
            (root/'health.json').write_text(json.dumps({'state':'running','pid':99999999}))
            (root/'jobs/taco--a/health.json').write_text(json.dumps({'state':'running','pid':99999999,'updated':time.time()}))
            c=probe.collect_root(root,'college',time.time())[0]
            self.assertEqual(c['tasks'][0]['state'],'stopped')
            self.assertFalse(c['controller_alive'])

    def test_completed_grades_override_stale_task_health(self):
        with tempfile.TemporaryDirectory() as path:
            root=Path(path);(root/'jobs/lats--a').mkdir(parents=True);(root/'grades/lats--a').mkdir(parents=True)
            (root/'protocol.json').write_text(json.dumps({'methods':['lats'],'tasks':[{'task':'a'}]}))
            (root/'health.json').write_text(json.dumps({'state':'running','pid':99999999}))
            (root/'jobs/lats--a/health.json').write_text(json.dumps({'state':'awaiting_grade'}))
            (root/'grades/lats--a/result.json').write_text(json.dumps({'grading_state':'complete','f2p':{'step_score':1},'official_success':True}))
            c=probe.collect_root(root,'college',time.time())[0]
            self.assertEqual(c['tasks'][0]['state'],'graded')
            self.assertEqual(c['tasks'][0]['score'],1)

    def test_cube_partitions_do_not_double_count_preserved_grades(self):
        graded=[task(str(i),'graded',score=1) for i in range(15)]
        master=campaign('college','grader',graded+[task(str(i),'pending') for i in range(15,20)])
        worker0=campaign('cube0','worker0',[task('15','running',20,'cube0'),task('16','running',20,'cube0')],101)
        worker1=campaign('cube1','worker1',[task('17','running',20,'cube1'),task('18','running',20,'cube1'),task('19','running',20,'cube1')],102)
        states={node:{'ok':True,'data':{'campaigns':[c]}} for node,c in [('college',master),('cube0',worker0),('cube1',worker1)]}
        c=reconcile(states)[0]
        self.assertEqual(c['graded_count'],15);self.assertEqual(c['active_count'],5)
        self.assertEqual(len(c['tasks']),20);self.assertEqual(c['node'],'college')

    def test_new_recovery_supersedes_old_failure_and_inherits_completed_tasks(self):
        old=campaign('college','old',[task('a','failed')],100,'old-source',1)
        new=campaign('college','new',[task('a','running')],200,'new-source',1)
        states={'college':{'ok':True,'data':{'campaigns':[old,new]}}}
        c=reconcile(states)[0]
        self.assertEqual(c['root'],'new');self.assertEqual(c['failed_count'],0)

    def test_single_task_repair_without_manifest_keeps_other_verified_scores(self):
        old=campaign('college','old',[task('a','graded',score=1),task('b','graded',score=.5)],100,'old',2)
        new=campaign('college','new',[task('a','failed')],200,'new',2)
        c=reconcile({'college':{'ok':True,'data':{'campaigns':[old,new]}}})[0]
        self.assertEqual(c['graded_count'],1)
        self.assertEqual(c['failed_count'],1)
        self.assertEqual({t['task'] for t in c['tasks']},{'a','b'})

    def test_offline_keeps_last_snapshot_and_explicit_staleness(self):
        states={'college':{'ok':True,'data':{'campaigns':[campaign('college','root',[task('a','running')])]}}}
        update_state(states,{'id':'college','ok':False,'error':'连接超时'})
        self.assertTrue(states['college']['data']['campaigns'])
        self.assertIn('离线',reconcile(states)[0]['status'])

    def test_budget_submission_is_not_an_engineering_failure(self):
        c=campaign('college','root',[task('a','graded',score=0)],expected=1)
        r=summarize(c)
        self.assertEqual(r['status'],'已全部完成');self.assertEqual(r['failed_count'],0)
        self.assertEqual(r['successes'],0)

    def test_latest_multi_method_campaigns_are_separate(self):
        a=campaign('college','root',[task('a','graded',score=.5)],expected=1)
        b=copy.deepcopy(a);b.update(method='lats',id='college|root|lats')
        result=reconcile({'college':{'ok':True,'data':{'campaigns':[a,b]}}})
        self.assertEqual({c['method'] for c in result},{'taco','lats'})


if __name__=='__main__':unittest.main()
