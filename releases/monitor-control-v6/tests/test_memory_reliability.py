import json
from pathlib import Path
import sys
import tempfile
import unittest
from dataclasses import replace
from collections import OrderedDict

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'sources/bestfgs-project/src'),str(ROOT/'sources/bestfgs-project/tests')]
from bestfgs.lean_memory import Memories,action_key
from bestfgs.memory_events import dependency_paths
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_protocol import LeanConfig
from bestfgs.lean_audit import read_trace
from bestfgs.models import TaskSpec
from test_lean import FakeEnvironment,Scripted,SUBMIT,run_action


def candidate(**extra):
    return dict(conclusion='The config parser rejected this input.',condition='Same input and parser configuration.',
        kind='blocker',operation='parse',targets=['config.txt'],next_step='Inspect config encoding',evidence_ids=['E1'])|extra


class MemoryReliabilityTests(unittest.TestCase):
    def exercise(self, actions, **overrides):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        cfg=LeanConfig(**(dict(memory_reliability=True,auto_memory=True,max_turns=50,max_tools=40,
            monitor_cooldown_tools=20,monitor_interval_tools=24,max_advisor_calls=0)|overrides))
        actor,mon=Scripted(actions),Scripted([])
        runner=LeanTaskRunner(FakeEnvironment(),actor,Scripted([]),cfg,Path(tmp.name)/'audit',monitor_client=mon)
        result=runner.run(TaskSpec('fixture','Fix the config parser'))
        events=read_trace(Path(tmp.name)/'audit/events.jsonl')
        self.assertIsNone(result['error_type'],result)
        return result,runner,events,actor

    def test_real_failure_lengths_repair_optional_field_not_core_memory(self):
        for size in (123,143):
            store=Memories(reliable=True)
            item,new=store.admit(candidate(operation='x'*size),{'E1':{'after':'same'}},{'E1'},
                                  lambda paths:{p:'file:stable' for p in paths},current_scope='same')
            self.assertTrue(new); self.assertEqual(item['operation'],'')
            self.assertEqual(item['repairs'][0]['original_chars'],size)
            self.assertEqual(item['conclusion'],candidate()['conclusion'])
            self.assertEqual(item['evidence_ids'],['E1'])

    def test_invalid_mandatory_fields_and_foreign_evidence_still_rejected(self):
        for extra in [dict(conclusion=''),dict(condition=''),dict(evidence_ids=['E99']),
                      dict(targets=['../outside']),dict(operation=[]),dict(kind={})]:
            with self.assertRaises(ValueError):
                Memories(reliable=True).admit(candidate(**extra),{'E1':{'after':'same'}},{'E1'},lambda p:{})

    def test_historical_fact_survives_unrelated_edit_with_captured_dependencies(self):
        store=Memories(reliable=True)
        evidence={'E1':dict(after='old-workspace',stable_dependencies={'config.txt':'file:original'})}
        item,_=store.admit(candidate(),evidence,{'E1'},lambda p:{k:'file:original' for k in p},current_scope='new-workspace')
        self.assertIn('unchanged',store.applicability(item,'new-workspace',{'config.txt':'file:original'}))
        self.assertIn('recheck_required',store.applicability(item,'new-workspace',{'config.txt':'file:changed'}))

    def test_old_fact_cannot_be_rebound_to_new_dependency(self):
        store=Memories(reliable=True)
        item,_=store.admit(candidate(),{'E1':dict(after='old')},{'E1'},lambda p:{k:'file:NEW' for k in p},current_scope='new')
        self.assertEqual(item['dependency_state'],{'config.txt':'unknown'})
        self.assertNotIn('unchanged',store.applicability(item,'new',{'config.txt':'file:NEW'}))

    def test_conflicting_dependency_versions_remain_uncertain(self):
        store=Memories(reliable=True)
        evidence={'E1':dict(after='a',stable_dependencies={'config.txt':'file:a'}),
                  'E2':dict(after='b',stable_dependencies={'config.txt':'file:b'})}
        item,_=store.admit(candidate(evidence_ids=['E1','E2']),evidence,set(evidence),lambda p:{'config.txt':'file:b'},current_scope='b')
        self.assertEqual(item['dependency_state']['config.txt'],'unknown')

    def test_irrelevant_recall_returns_nothing_and_validity_precedes_overlap(self):
        store=Memories(reliable=True)
        item,_=store.admit(candidate(),{'E1':dict(after='same')},{'E1'},lambda p:{'config.txt':'file:a'},current_scope='same')
        self.assertEqual(store.recall('unrelated astronomy','same',{'config.txt':'file:a'}),[])
        self.assertEqual(store.recall('config parser','same',{'config.txt':'file:a'})[0]['id'],item['id'])

    def test_findings_and_shared_target_do_not_block_unrelated_action(self):
        store=Memories(reliable=True)
        store.admit(candidate(kind='finding'),{'E1':dict(after='same')},{'E1'},lambda p:{'config.txt':'file:a'},current_scope='same')
        self.assertEqual(store.match_action(run_action('parse','config.txt'),'same',{'config.txt':'file:a'}),[])
        store.admit(candidate(conclusion='Different blocker'),{'E1':dict(after='same')},{'E1'},lambda p:{'config.txt':'file:a'},current_scope='same')
        self.assertEqual(store.match_action(run_action('cat','config.txt'),'same',{'config.txt':'file:a'}),[])

    def test_execution_observer_works_without_monitor_calls(self):
        result,runner,events,actor=self.exercise([run_action('fail')]*2+[SUBMIT])
        self.assertTrue(result['submitted']); self.assertEqual(result['monitor_rounds'],0)
        self.assertEqual(runner.counts['observed_memories_admitted'],1)
        self.assertEqual(actor.prompts[-1]['fixed_context']['memories'][0]['origin'],'execution_observer')
        self.assertTrue(any(e['event']=='memory_event_candidate' for e in events))

    def test_acknowledgment_without_reason_is_not_automatic_bypass(self):
        result,runner,events,_=self.exercise([run_action('fail')]*2+
            [run_action('fail',uses_memory=['M1']),run_action('write','new route'),SUBMIT])
        self.assertTrue(result['submitted']); self.assertEqual(result['tool_calls'],3)
        self.assertEqual(runner.counts['memory_interventions'],1)
        self.assertTrue(any(e['event']=='memory_followup_outcome' for e in events))

    def test_reasoned_retry_executes_and_repeated_outcome_is_recorded(self):
        result,runner,events,_=self.exercise([run_action('fail')]*2+
            [run_action('fail',uses_memory=['M1'],memory_reason='Check whether the transient dependency recovered.'),SUBMIT])
        self.assertTrue(result['submitted']); self.assertEqual(result['tool_calls'],3)
        self.assertEqual(runner.counts['memory_interventions'],0)
        self.assertTrue(any(e['event']=='memory_retry_no_new_outcome' for e in events))

    def test_public_test_result_is_observation_not_success_claim(self):
        result,runner,events,actor=self.exercise([run_action('pytest','config.txt'),SUBMIT])
        item=next(iter(runner.memory.items.values()))
        self.assertEqual(item['kind'],'finding')
        self.assertIn('unverified',item['conclusion'])
        self.assertEqual(item['status'],'observed_tool_outcome_not_causal_rule')

    def test_optional_repair_visible_in_runtime_audit(self):
        result,runner,events,actor=self.exercise([run_action('read'),run_action('read',memory=candidate(operation='x'*143)),SUBMIT],auto_memory=False)
        self.assertTrue(result['submitted'])
        self.assertTrue(any(e['event']=='memory_field_repaired' for e in events))
        self.assertTrue(actor.prompts[-1]['fixed_context']['memory_reliability']['notices'])

    def test_execution_time_dependencies_recorded(self):
        result,runner,events,_=self.exercise([run_action('fail','config.txt'),SUBMIT])
        row=runner.evidence['E1']
        self.assertEqual(row['stable_dependencies'],{'config.txt':'missing'})
        self.assertIn('dynamic_dependencies_unknown',row['dependency_coverage'])

    def test_parser_paths_bounded_and_no_private_or_shell_expansion(self):
        paths=dependency_paths(run_action('python','tool.py','/tests/hidden.py','../outside','$(secret).txt','config.json',cwd='/app/sub'))
        self.assertIn('sub/tool.py',paths); self.assertIn('sub/config.json',paths)
        self.assertFalse(any('hidden' in p or 'secret' in p or '..' in p for p in paths))
        self.assertLessEqual(len(dependency_paths(run_action('cat',*[f'f{i}.txt' for i in range(100)]))),16)

    def test_same_lesson_merges_new_evidence_and_preserves_capacity(self):
        store=Memories(capacity=2,reliable=True)
        evidence={f'E{i}':dict(after='same') for i in range(1,4)}
        a,_=store.admit(candidate(),evidence,set(evidence),lambda p:{'config.txt':'file:a'},current_scope='same')
        b,added=store.admit(candidate(evidence_ids=['E2']),evidence,set(evidence),lambda p:{'config.txt':'file:a'},current_scope='same')
        self.assertFalse(added); self.assertEqual(a['id'],b['id']); self.assertEqual(b['reinforcements'],2)

    def test_observed_memory_not_created_when_feature_off(self):
        result,runner,_,_=self.exercise([run_action('fail')]*2+[SUBMIT],auto_memory=False)
        self.assertEqual(runner.counts['observed_memories_admitted'],0)
        self.assertEqual(len(runner.memory.items),0)

    def test_actual_two_rejected_candidates_preserve_core_and_repair(self):
        rows=json.loads((ROOT/'evidence/previous-rejected-candidates.json').read_text())
        self.assertEqual(len(rows),2)
        for row in rows:
            evidence={e['id']:e for e in row['evidence']}
            item,added=Memories(reliable=True).admit(row['candidate'],evidence,set(evidence),
                lambda paths:{p:'unknown' for p in paths},current_scope=row['scope'])
            self.assertTrue(added); self.assertEqual(item['operation'],'')
            self.assertEqual(item['conclusion'],row['candidate']['conclusion'])
            self.assertEqual(item['evidence_ids'],row['candidate']['evidence_ids'])

    def test_retention_prefers_current_reinforced_lesson_over_stale(self):
        store=Memories(capacity=2,reliable=True)
        current=lambda paths:{p:'file:new' for p in paths}
        evidence={'E1':dict(after='a',stable_dependencies={'config.txt':'file:new'}),
                  'E2':dict(after='b',stable_dependencies={'config.txt':'file:old'}),
                  'E3':dict(after='c',stable_dependencies={'config.txt':'file:new'})}
        first,_=store.admit(candidate(),evidence,set(evidence),current,current_scope='c')
        stale,_=store.admit(candidate(conclusion='stale',evidence_ids=['E2']),evidence,set(evidence),current,current_scope='c')
        store.admit(candidate(conclusion='new',evidence_ids=['E3']),evidence,set(evidence),current,current_scope='c')
        self.assertIn(first['id'],store.items); self.assertNotIn(stale['id'],store.items)
        self.assertEqual(len(store.items),2)

    def test_auto_candidate_historical_scope_uses_observed_file_versions(self):
        _,runner,_,_=self.exercise([SUBMIT],auto_memory=False)
        runner.monitor_review={'id':'R1'}
        evidence={'E1':dict(after='old',stable_dependencies={'config.txt':'missing'},stdout='',stderr='parser failed')}
        value=candidate(support=[dict(evidence_id='E1',field='stderr',quote='parser failed')])
        runner._admit_auto_memory(value,evidence)
        item=next(iter(runner.memory.items.values()))
        self.assertEqual(item['dependency_state'],{'config.txt':'missing'})
        self.assertEqual(item['scope'],'old')
        self.assertIn('unchanged',runner.memory.applicability(item,runner.environment.scope(),{'config.txt':'missing'}))

    def test_deferred_event_survives_recent_window(self):
        _,runner,_,_=self.exercise([run_action('fail','config.txt'),SUBMIT])
        first=dict(runner.evidence['E1'])
        runner.evidence=OrderedDict((f'E{i}',dict(first,id=f'E{i}')) for i in range(40,56))
        payload=runner._monitor_payload('test_pending')
        self.assertIn('E1',[e['id'] for e in payload['evidence']])
        self.assertTrue(next(e for e in payload['evidence'] if e['id']=='E1')['deferred_historical_event'])

    def test_half_monitor_allowance_reserved_for_later_phase(self):
        _,runner,events,_=self.exercise([run_action('read'),SUBMIT])
        runner.config=replace(runner.config,max_tools=600,max_monitor_calls=12)
        runner.counts['monitor_calls']=6; runner.counts['tool_calls']=96
        runner._maybe_monitor()
        self.assertEqual(runner.counts['monitor_calls'],6)
        self.assertEqual(runner.clients['monitor'].prompts,[])


if __name__=='__main__': unittest.main()
