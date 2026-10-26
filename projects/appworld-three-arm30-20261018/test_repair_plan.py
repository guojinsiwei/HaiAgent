import unittest
from repair_plan import make_plan
class PlanTests(unittest.TestCase):
    def test_only_unpassed_affected_trials_retry_and_unstarted_work_is_preserved(self):
        p={'methods':['hld','kzdsh-new','recuris','dsh'],'tasks':[{'task':'a'},{'task':'b'}]}
        done=[{'job':'hld--a','task':'a','arm':'hld','official_success':True,'repair_cause':'legacy_cache_price_overcount'},
              {'job':'kzdsh-new--a','task':'a','arm':'kzdsh-new','official_success':False,'repair_cause':'legacy_cache_price_overcount'},
              {'job':'dsh--a','task':'a','arm':'dsh','official_success':False}]
        x=make_plan(p,done)
        self.assertEqual(x['retry_count'],1);self.assertEqual(x['unstarted_count'],5)
        self.assertEqual(x['queue'][0]['row']['_job'],'kzdsh-new--a--repair1')
        self.assertEqual(x['previous_completed'],done)
        identities=[(i['arm'],i['row']['task']) for i in x['queue']]
        self.assertEqual(len(identities),len(set(identities)))
        self.assertNotIn(('hld','a'),identities);self.assertNotIn(('dsh','a'),identities)
        done[1]['actual_budget_exhausted']=True
        self.assertEqual(make_plan(p,done)['retry_count'],0)
if __name__=='__main__':unittest.main()
