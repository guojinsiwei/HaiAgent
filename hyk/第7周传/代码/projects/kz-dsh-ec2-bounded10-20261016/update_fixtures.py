from pathlib import Path
import json
P=Path(__file__).resolve().parent
def edit(path,old,new):
    path=P/path;t=path.read_text();assert old in t,(path,old);path.write_text(t.replace(old,new))
edit('tests/host.test.mjs',"import test from 'node:test';","import test from 'node:test';\nimport {fixtureReview} from './review-fixture.mjs';")
edit('tests/host.test.mjs','      if(this.roleReply)value=this.roleReply(payload,value);','      if(this.roleReply)value=this.roleReply(payload,value);\n      if(!this.rawReview)value=fixtureReview(payload,value);')
edit('tests/host.test.mjs','/critic_unavailable/','/missing_information/')
edit('tests/host.test.mjs',"saved.full.critic.decision,'review_unavailable');\n  assert.equal(saved.full.usage.roles.critic,1);assert.equal(adapter.solver,3)","saved.full.critic.decision,'repair_check');\n  assert.equal(saved.full.usage.roles.critic,1);assert.equal(adapter.solver,3)")
edit('tests/subgoal-integration-repair4.test.mjs',"import test from 'node:test';","import test from 'node:test';\nimport {fixtureReview} from './review-fixture.mjs';")
edit('tests/subgoal-integration-repair4.test.mjs',"      block={type:'text',text:JSON.stringify(value)};","      value=fixtureReview(payload,value);\n      block={type:'text',text:JSON.stringify(value)};")
edit('tests/evidence-control.test.mjs',"const accepted={decision:'accept',requirements:['public behavior'],gaps:[]};","const accepted={decision:'accept',requirements:['public behavior'],gaps:[],gap_updates:[{gap_id:'Gap-1',status:'closed',evidence_ids:['E1'],reason:'The targeted parser check verifies its declared behavior.'}]};\nconst mappedReceipt={evidence_id:'E1',passed:true,gap_ids:['Gap-1'],requirement_quotes:['parser'],basis:{level:'attributed_correctness_basis'}};")
edit('tests/evidence-control.test.mjs',"[{evidence_id:'E1',passed:true}]","[mappedReceipt]")
edit('tests/evidence-control.test.mjs',"gap_id:'Gap-1',status:'closed',evidence_ids:['E1']}]},[mappedReceipt]","gap_id:'Gap-1',status:'closed',evidence_ids:['E1'],reason:'Parser test targets this requirement.'}]},[mappedReceipt]")
edit('tests/evidence-control.test.mjs',"ledger.record(accepted,[],{accepted:true,scope:U,dependencies:{'a.py':'unknown'},observed:4});","ledger.record(accepted,[mappedReceipt],{accepted:true,scope:U,dependencies:{'a.py':'unknown'},observed:4,evidence:{E1:row()}});")
edit('src/roles.mjs','An invalid test invocation is repair_check','An invalid test invocation is a check defect (repair_check)')
edit('deploy/terminalbench/bounded_runtime.py',"    tasks=json.loads", "    p=kz/'boot-guard.mjs';p.write_text(p.read_text().replace(\"budgetMode==='unlimited'\",\"budgetMode==='bounded_peak_price_estimate'\").replace('unbounded accounting unavailable','bounded accounting unavailable'))\n    tasks=json.loads")
for name in ('prepare.py','seal.py'):
    p=P/'deploy/terminalbench'/name;t=p.read_text().replace('0.3.1','0.3.2').replace('evidence-control-2','evidence-control-3');p.write_text(t)
for name in ('package.json','package-lock.json'):
    p=P/name;doc=json.loads(p.read_text());doc['version']='0.3.2'
    if name=='package-lock.json':doc['packages']['']['version']='0.3.2'
    p.write_text(json.dumps(doc,indent=2))

# Supervisor test doubles do not open a real budget service. Verify the new
# single-pass contract while preserving the existing recovery/lifecycle cases.
edit('deploy/terminalbench/test_campaign.py','class CampaignTests(unittest.TestCase):', '''class FakeBudget:
    def __init__(self,*a,**kw):self.url='http://offline.invalid';self.token='fixture'
    def snapshot(self):return {'halt_reason':None}
    def close(self):pass

class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.budget_patch=patch.object(c,'BudgetService',FakeBudget);self.budget_patch.start();self.addCleanup(self.budget_patch.stop)
''')
edit('deploy/terminalbench/test_campaign.py',"self.assertEqual(state['summary']['kz-dsh']['retry_total'],1)","self.assertEqual(state['summary']['kz-dsh']['retry_total'],0)")
edit('deploy/terminalbench/test_campaign.py',"            first_retry=next(i for i,j in enumerate(launched) if 'retry-' in j)\n            self.assertTrue(all('first-' not in j for j in launched[first_retry:]))","            self.assertFalse(any('retry-' in j for j in launched))")
edit('deploy/terminalbench/test_campaign.py',"self.assertEqual(after['summary']['kz-dsh']['retry_total'],1)","self.assertEqual(after['summary']['kz-dsh']['retry_total'],0)")
print('Explicit-protocol test fixtures and bounded deployment updated.')
