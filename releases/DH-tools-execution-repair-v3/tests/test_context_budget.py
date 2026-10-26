"""Long-context and failure-classification regression; no external model API."""
from copy import deepcopy
from dataclasses import replace
import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.context_budget import ContextBudgetError,fit_payload,message_bytes,bounded_observation,evidence_view
from bestfgs.lean_conversation import Conversation,message_chars
from bestfgs.code_tools import ToolTaskRunner,TOOL_DRIVER
from bestfgs.error_routing import RoutingPolicy
from bestfgs.lean_protocol import LeanConfig
from bestfgs.models import TaskSpec
from test_code_tools import ToolEnvironment
from test_lean import Scripted,SUBMIT

class ContextTests(unittest.TestCase):
    def test_actual_cmu_p2_failure_preserves_task_memory_and_subgoals(self):
        fixture=json.loads((ROOT/'evidence/current-failure-context.json').read_text(encoding='utf-8'))
        p=fixture['payload'];original=deepcopy(p)
        view,stats=fit_payload(fixture['system'],p,44976)
        self.assertGreater(stats['original_bytes'],100000)
        self.assertLessEqual(stats['input_bytes'],44976)
        self.assertEqual(view['task'],original['task'])
        self.assertEqual(view['fixed_context']['memories'],original['fixed_context']['memories'])
        self.assertEqual(view['fixed_context']['subgoals'],original['fixed_context']['subgoals'])
        self.assertEqual(p,original)

    def test_full_request_bytes_with_multibyte_and_large_feedback(self):
        memories=[{'id':'M1','condition':'条件','conclusion':'不可重复此操作','evidence_ids':['E1']}]
        goals={'goals':[{'id':'G1','status':'needs_work'}]}
        p={'task':{'goal':'public requirement'},'fixed_context':{'memories':memories,'subgoals':goals,
           'evidence':[{'id':'E1','stdout':'中'*10000}],
           'feedback':{'action_loop':{'evidence_id':'E1','prior_result':{'stdout':'中'*20000}}},
           'contrastive_exploration':{'negative_anchors':[{'id':'F1','observation':'中'*10000}]}},
           'recent_decisions':[{'action':'old','detail':'中'*10000}]*6}
        original=deepcopy(p);system='instruction '*1300
        view,stats=fit_payload(system,p,44976)
        self.assertLessEqual(message_bytes([{'role':'system','content':system},
             {'role':'user','content':json.dumps(view,ensure_ascii=False)}]),44976)
        self.assertEqual(view['fixed_context']['memories'],memories)
        self.assertEqual(view['fixed_context']['subgoals'],goals)
        self.assertEqual(view['task'],p['task']);self.assertEqual(p,original)
        self.assertTrue(view['context_projection']['partial_fields'])
        self.assertIn('partial context excerpt',json.dumps(view,ensure_ascii=False))
    def test_archive_index_cannot_kill_a_request_that_fits_without_history(self):
        c=Conversation(byte_budget=True)
        for i in range(500):c.append({'action':'run','number':i},{'stdout':'中'*2000})
        system='sys';p={'task':'public'}
        base=message_bytes([{'role':'system','content':system},
            {'role':'user','content':json.dumps(p,ensure_ascii=False)}])
        h,v=c.build(system,p,base+10)
        self.assertEqual(h,[]);self.assertTrue(v['archive_notice_omitted'])
        self.assertEqual(len(c.turns),500)
        self.assertEqual(c.retrieve({'turn_ids':[1],'offset':0})['history_records'][0]['turn_id'],1)
    def test_compiled_driver_never_enters_tool_action_or_history(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        runner=ToolTaskRunner(ToolEnvironment(),Scripted([{'action':'inspect_code','path':'f.py'},SUBMIT]),
            Scripted([]),LeanConfig(max_turns=10,max_tools=10,subgoals_enabled=True,memory_decision=False),
            Path(tmp.name)/'trace',routing=RoutingPolicy())
        r=runner.run(TaskSpec('fixture','public'));cmd=runner.environment.executed[0]
        self.assertEqual(cmd['argv'],['dh-tool','inspect_code','read','f.py'])
        self.assertNotIn(TOOL_DRIVER,json.dumps(runner.conversation.turns))
        self.assertNotIn('_native_request',runner._action_core(cmd))
    def test_impossible_task_is_local_context_error_not_model_protocol_or_recovery(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);actor=Scripted([])
        runner=ToolTaskRunner(ToolEnvironment(),actor,Scripted([]),
            LeanConfig(max_turns=10,max_tools=10,subgoals_enabled=True,memory_decision=False),
            Path(tmp.name)/'trace',routing=RoutingPolicy())
        r=runner.run(TaskSpec('fixture','中'*30000))
        self.assertEqual(r['stop_reason'],'context_budget_error')
        self.assertEqual(r['mechanism_utilization']['protocol_errors'],0)
        self.assertEqual(r['interaction_rounds'],0);self.assertEqual(len(actor.prompts),0)
        self.assertEqual(r['mechanism_utilization']['context_budget_errors'],1)
    def test_120_native_actions_remain_within_byte_budget(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        class LongOutputEnvironment(ToolEnvironment):
            def execute(self,action,deadline):
                result=super().execute(action,deadline)
                return replace(result,stdout=json.dumps({'lines':[{'line':i,'text':'中'*100}
                    for i in range(70)]},ensure_ascii=False))
        actor=Scripted([{'action':'inspect_code','path':'f'+str(i)+'.py'} for i in range(120)]+[SUBMIT])
        runner=ToolTaskRunner(LongOutputEnvironment(),actor,Scripted([{'alternatives':[]}]*12),
            LeanConfig(max_turns=130,max_tools=130,subgoals_enabled=True,memory_decision=False,
                       context_chars=46000),Path(tmp.name)/'trace',routing=RoutingPolicy())
        r=runner.run(TaskSpec('fixture','public requirement'))
        self.assertTrue(r['submitted'],repr(r));self.assertEqual(r['tool_calls'],120)
        self.assertEqual(r['mechanism_utilization']['protocol_errors'],0)
        for p in actor.prompts:self.assertTrue(p['context_projection']['task_and_memories_complete'])
        for line in (Path(tmp.name)/'trace/events.jsonl').read_text(encoding='utf-8').splitlines():
            event=json.loads(line)
            if event['event']=='final_prompt':self.assertLessEqual(message_bytes(event['messages']),44976)

    def test_memory_reserve_counts_utf8_and_keeps_whole_records(self):
        from bestfgs.memory_injection import reserved_view
        records=[{'id':'M'+str(i),'conclusion':'中'*1200,'evidence_ids':['E1']} for i in range(6)]
        shown,omitted=reserved_view(records,8000,byte_budget=True)
        self.assertLessEqual(len(json.dumps(shown,ensure_ascii=False).encode('utf-8')),8000)
        self.assertEqual(len(shown)+len(omitted),6)
        for m in shown:self.assertEqual(m['conclusion'],'中'*1200)

    def test_dependency_maps_and_duplicate_feedback_are_only_prompt_views(self):
        dependencies={'src/'+str(i)+'.cpp':'file:'+str(i).zfill(64) for i in range(60)}
        row={'id':'E47','return_code':0,'stdout':'SUCCESS '+('中'*2000),'stderr':'','argv':'python check.py',
             'dependency_before':dependencies,'dependency_after':dependencies,'stable_dependencies':dependencies,
             'relevant_dependencies':dependencies,'before':'same','after':'same'}
        memories=[{'id':'M1','conclusion':'keep the original criterion','evidence_ids':['E47']}]
        p={'task':{'goal':'public task'},'fixed_context':{'evidence':[row]*6,
            'feedback':{'evidence':row},'memories':memories,'subgoals':{'goals':[{'id':'G1','status':'pending'}]}}}
        original=deepcopy(p);view,stats=fit_payload('instruction '*1300,p,44976)
        self.assertEqual(p,original);self.assertEqual(view['fixed_context']['memories'],memories)
        self.assertNotIn('evidence',view['fixed_context']['feedback'])
        self.assertEqual(view['fixed_context']['feedback']['evidence_id'],'E47')
        self.assertNotIn('dependency_before',view['fixed_context']['evidence'][-1])
        self.assertEqual(view['fixed_context']['evidence'][-1]['return_code'],0)
        self.assertLessEqual(stats['input_bytes'],44976)

    def test_unforeseen_wide_metadata_cannot_escape_byte_admission(self):
        giant={('file'+str(i)+'.py'):('中'*150) for i in range(400)}
        p={'task':{'goal':'complete public specification'},'fixed_context':{
            'new_future_panel':giant,'feedback':giant,'memories':[{'id':'M1','conclusion':'must survive'}],
            'subgoals':{'goals':[{'id':'G1','status':'pending'}]}}}
        view,stats=fit_payload('system '*1800,p,44976)
        self.assertLessEqual(stats['input_bytes'],44976)
        self.assertTrue(view['fixed_context']['new_future_panel']['prompt_view_partial'])
        self.assertEqual(view['fixed_context']['memories'],p['fixed_context']['memories'])
        self.assertEqual(list(view)[-1],'fixed_context')

    def test_dependency_partial_capture_does_not_invent_a_change(self):
        row={'id':'E1','dependency_before':{'x':'file:a'},'dependency_after':{'y':'file:b'}}
        view=evidence_view(row)['dependency_observation']
        self.assertEqual(view['changed_paths'],[]);self.assertEqual(view['unknown_path_count'],2)
        oversized={'enormous_key'*1000:'中'*10000}
        self.assertLessEqual(len(json.dumps(bounded_observation(oversized,1000),ensure_ascii=False).encode()),1000)

if __name__=='__main__':unittest.main()
