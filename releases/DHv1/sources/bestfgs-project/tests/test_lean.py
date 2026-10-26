"""Behavioral regression tests: no real model API, Docker daemon or credentials."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from bestfgs.lean_audit import read_trace, digest
from bestfgs.lean_protocol import LeanConfig, parse_action
from bestfgs.lean_runtime import LeanTaskRunner
from bestfgs.lean_environment import LiveWorkspace
from bestfgs.lean_memory import Memories
from bestfgs.lean_progress import DeliveryProgress, requested_artifacts
from bestfgs.models import CommandSpec, CommandResult, TaskSpec, ModelCallError


class Scripted:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []
    def complete_json(self, **kwargs):
        self.prompts.append(json.loads(kwargs['user_prompt']))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class FakeEnvironment:
    def __init__(self):
        self.value = 'seed'
        self.dependencies = {}
        self.executed, self.saved, self.deliveries = [], {}, 0
    def scope(self):
        return digest(self.value)
    def execute(self, action, deadline):
        self.executed.append(action)
        args = action['argv']
        if args[0] == 'write':
            self.value = args[1]
        if args[0] == 'artifact':
            self.dependencies[args[1]] = 'file:' + args[2]
            self.value = self.value + ':' + args[1] + ':' + args[2]
        failed = args[0] == 'fail'
        return CommandResult(CommandSpec(tuple(args), 'fixture'), int(failed), self.value,
                             'same error' if failed else '', 0)
    def checkpoint(self, label):
        cid = 'snap' + str(len(self.saved))
        self.saved[cid] = self.value
        return dict(id=cid, fingerprint=self.scope(), path=cid, label=label)
    def restore(self, record):
        self.value = self.saved[record['id']]
    def dependency_state(self, paths):
        return {path:self.dependencies.get(path, 'missing') for path in paths}
    def delivery(self):
        self.deliveries += 1
        return dict(value=self.value, fingerprint=self.scope())


def run_action(*argv, **extra):
    return dict(action='run', argv=list(argv), purpose='test', **extra)


SUBMIT = dict(action='submit', summary='deliver current files')
ADVICE = dict(alternatives=[dict(hypothesis='Input encoding may be wrong',
    check='Inspect the header bytes', difference='Inspect the input instead of retrying the parser', evidence_ids=['E3'])])


def memory_response(action, decision='recheck'):
    """Migrate legacy scripted replies, without disabling the production protocol."""
    review = dict(ids=['M1'], observed_result='The advertised memory records the prior config observation.',
                  applicability='Check whether this evidence still applies to the current workspace.',
                  decision=decision, reason='Use or recheck the supplied evidence before this action.')
    if decision == 'justified_retry':
        review['new_evidence'] = 'Execute the explicitly proposed parser check once and compare its result.'
    return dict(memory_review=review, strategy_adjustment='Perform the selected concrete action and inspect its result.', **action)


class LeanTests(unittest.TestCase):
    def exercise(self, actions, advice=(), config=None, feedback=None, env=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        environment = env or FakeEnvironment()
        actor, advisor = Scripted(actions), Scripted(advice)
        runner = LeanTaskRunner(environment, actor, advisor,
            config or LeanConfig(max_turns=30, max_tools=20), Path(tmp.name)/'audit', feedback,
            secrets=('fixture-secret-value',))
        result = runner.run(TaskSpec('fixture', 'Create useful output'))
        events = read_trace(Path(tmp.name)/'audit/events.jsonl')
        return result, events, actor, advisor, environment, runner

    def test_continuous_actions_need_no_auxiliary_call_or_per_command_snapshot(self):
        result, events, actor, advisor, env, _ = self.exercise(
            [run_action('write','A'), run_action('read'), run_action('write','B'), SUBMIT])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['artifact']['value'], 'B')
        self.assertEqual(result['interaction_rounds'], 4)
        self.assertEqual(result['tool_calls'], 3)
        self.assertEqual(len(advisor.prompts), 0)
        self.assertEqual(len(env.saved), 1)
        self.assertEqual(env.deliveries, 1)
        self.assertIsNone(result['official_success'])
        self.assertIsNone(result['contextual_tool_redundancy']['rate'])
        self.assertEqual([e['event'] for e in events].count('submission'),1)

    def test_repeated_failure_calls_advisor_then_main_changes_action(self):
        result, events, actor, advisor, env, _ = self.exercise(
            [run_action('fail')]*3 + [run_action('write','new method'),SUBMIT], [ADVICE])
        self.assertEqual(len(advisor.prompts),1)
        self.assertEqual(result['interaction_rounds'],6)
        self.assertEqual(actor.prompts[3]['fixed_context']['advice']['alternatives'][0]['hypothesis'],
                         'Input encoding may be wrong')
        self.assertEqual(env.value,'new method')
        self.assertEqual(result['mechanism_utilization']['advisor_responses_accepted'],1)

    def test_repeated_read_is_not_automatically_a_failure(self):
        result, _, _, advisor, _, _ = self.exercise([run_action('read')]*8+[SUBMIT])
        self.assertEqual(len(advisor.prompts),0)
        self.assertTrue(result['submitted'])

    def test_extended_diagnosis_gets_nudge_then_bounded_advice(self):
        config=LeanConfig(diagnostic_nudge_threshold=3,diagnostic_advisor_threshold=5,
                          advisor_cooldown_tools=1)
        actions=[run_action('cat','file.txt')]*5+[run_action('write','implementation'),SUBMIT]
        result, _, actor, advisor, _, _ = self.exercise(actions,[ADVICE],config)
        self.assertIn('diagnostic_nudge',actor.prompts[3]['fixed_context']['budget_pressure'])
        self.assertEqual(len(advisor.prompts),1)
        self.assertEqual(result['mechanism_utilization']['post_advice_actions'],1)

    def test_advisor_capacity_and_cooldown_do_not_stop_main(self):
        advice=dict(alternatives=[])
        actions=[dict(action='consult',question='Which input should I check?')]*4+[SUBMIT]
        result, _, _, advisor, _, _ = self.exercise(actions,[advice],LeanConfig(max_advisor_calls=1))
        self.assertEqual(len(advisor.prompts),1)
        self.assertTrue(result['submitted'])

    def test_explicit_branch_restore_keeps_current_attempt(self):
        actions=[run_action('write','good'),dict(action='checkpoint',label='good',hypothesis='retain solution'),
                 run_action('write','bad'),dict(action='restore',checkpoint_id='C2',reason='return to good'),SUBMIT]
        result, events, _, _, env, runner=self.exercise(actions)
        self.assertEqual(result['artifact']['value'],'good')
        self.assertIn('bad',env.saved.values())
        self.assertEqual(result['mechanism_utilization']['branch_restores'],1)
        self.assertEqual(len(runner.graph),3)

    def test_checkpoint_budget_refuses_restore_without_losing_current_files(self):
        actions=[run_action('write','good'),dict(action='checkpoint',label='good',hypothesis='retain'),
                 run_action('write','latest'),dict(action='restore',checkpoint_id='C1',reason='try root'),SUBMIT]
        result, _, _, _, env, _=self.exercise(actions,config=LeanConfig(max_active_checkpoints=2,max_checkpoints=2))
        self.assertEqual(env.value,'latest')
        self.assertEqual(result['mechanism_utilization']['protocol_errors'],1)

    def test_memory_preserved_but_marked_historical_after_restore(self):
        memory=dict(conclusion='Library parser expects UTF8',condition='for this input',evidence_ids=['E1'])
        actions=[run_action('write','new'),dict(action='checkpoint',label='new',hypothesis='keep',memory=memory),
                 memory_response(dict(action='restore',checkpoint_id='C1',reason='try alternative')),
                 memory_response(SUBMIT)]
        result, events, actor, _, _, _=self.exercise(actions)
        recalled=actor.prompts[-1]['fixed_context']['memories']
        self.assertEqual(recalled[0]['applicability'],'historical_recheck_required')
        self.assertEqual(result['mechanism_utilization']['memories_admitted'],1)
        self.assertGreater(result['mechanism_utilization']['memory_exposures'],0)

    def test_bad_optional_memory_does_not_discard_valid_command(self):
        actions=[run_action('write','A',memory={'conclusion':'x','condition':'y','evidence_ids':['E999']}),SUBMIT]
        result, _, _, _, env, _=self.exercise(actions)
        self.assertTrue(result['submitted'])
        self.assertEqual(env.value,'A')
        self.assertEqual(result['mechanism_utilization']['memories_rejected'],1)

    def test_memory_is_in_fixed_panel_after_old_history_eviction(self):
        memory=dict(conclusion='Use the UTF8 parser',condition='for this input',evidence_ids=['E1'])
        actions=[run_action('read'),run_action('read',memory=memory)] + [memory_response(run_action('read'))]*10 + [memory_response(dict(SUBMIT,uses_memory=['M1']))]
        result, events, actor, _, _, _=self.exercise(actions)
        self.assertEqual(actor.prompts[-1]['fixed_context']['memories'][0]['id'],'M1')
        self.assertEqual(result['mechanism_utilization']['memory_use_self_reports'],1)

    def test_action_conditioned_memory_reminds_before_execution_and_audits_followup(self):
        env=FakeEnvironment()
        env.dependencies['config.txt']='file:v1'
        memory=dict(kind='blocker',conclusion='Parsing this config directly failed',
            condition='while config.txt remains unchanged',operation='parse-config',
            targets=['config.txt'],next_step='Inspect its encoding first',evidence_ids=['E1'])
        actions=[run_action('read','config.txt'),dict(action='checkpoint',label='evidence',
            hypothesis='retain',memory=memory),memory_response(run_action('python','parse-config','config.txt')),
            memory_response(run_action('artifact','result.json','v1')),memory_response(SUBMIT)]
        result, events, actor, _, env, _=self.exercise(actions,env=env)
        self.assertEqual(result['mechanism_utilization']['memory_interventions'],1)
        self.assertEqual(result['mechanism_utilization']['memory_action_changed'],1)
        self.assertEqual(result['mechanism_utilization']['memory_followup_actions'],1)
        self.assertEqual(result['mechanism_utilization']['memory_followup_runs'],1)
        self.assertEqual(result['mechanism_utilization']['memory_followup_workspace_changed'],1)
        self.assertNotIn(['python','parse-config','config.txt'],[x['argv'] for x in env.executed])
        intervention=actor.prompts[3]['fixed_context']['memory_intervention']
        self.assertEqual(intervention['matched_memory_ids'],['M1'])
        self.assertIn('M1',[m['id'] for m in actor.prompts[3]['fixed_context']['memories']])
        followups=[e for e in events if e['event']=='memory_followup_outcome']
        self.assertEqual(followups[0]['intervention_id'],'MI1')
        self.assertFalse(followups[0]['causal_benefit_proven'])

    def test_deliberate_same_action_runs_after_one_memory_reminder(self):
        env=FakeEnvironment(); env.dependencies['config.txt']='file:v1'
        memory=dict(kind='procedure',conclusion='Parser is valid after checking encoding',
            condition='config unchanged',operation='parse-config',targets=['config.txt'],
            next_step='Run parser',evidence_ids=['E1'])
        proposal=memory_response(run_action('python','parse-config','config.txt'))
        deliberate=memory_response(dict(run_action('python','parse-config','config.txt'),uses_memory=['M1']), 'justified_retry')
        actions=[run_action('read','config.txt'),dict(action='checkpoint',label='evidence',
            hypothesis='retain',memory=memory),proposal,deliberate,memory_response(SUBMIT)]
        result, _, _, _, env, _=self.exercise(actions,env=env)
        self.assertEqual(result['mechanism_utilization']['memory_interventions'],1)
        self.assertEqual(result['mechanism_utilization']['memory_action_unchanged'],1)
        self.assertIn(['python','parse-config','config.txt'],[x['argv'] for x in env.executed])

    def test_memory_reconsideration_to_submit_does_not_leak_into_later_tool(self):
        env=FakeEnvironment(); env.dependencies['config.txt']='file:v1'
        memory=dict(kind='blocker',conclusion='Direct parsing failed repeatedly',
            condition='config unchanged',operation='parse-config',targets=['config.txt'],
            evidence_ids=['E1'])
        rejected=[True,False]
        def feedback(_artifact): return 'not yet' if rejected.pop(0) else None
        actions=[run_action('cat','config.txt'),dict(action='checkpoint',label='evidence',
            hypothesis='retain',memory=memory),memory_response(run_action('python','parse-config','config.txt')),
            memory_response(SUBMIT),memory_response(run_action('write','later-unrelated')),memory_response(SUBMIT)]
        result, events, _, _, _, _=self.exercise(actions,env=env,feedback=feedback)
        chains=[e for e in events if e['event']=='memory_followup_outcome']
        self.assertEqual(len(chains),1)
        self.assertEqual(chains[0]['action_kind'],'submit')
        self.assertFalse(chains[0]['outcome_observed'])
        self.assertEqual(result['mechanism_utilization']['memory_followup_runs'],0)

    def test_file_level_memory_survives_unrelated_workspace_change_but_not_target_change(self):
        memories=Memories()
        evidence={'E1':{'after':'scope-1'}}
        states={'config.txt':'file:v1'}
        item,added=memories.admit(dict(kind='finding',conclusion='Config is UTF8',
            condition='this file version',targets=['config.txt'],evidence_ids=['E1']),
            evidence,{'E1'},lambda paths:{p:states.get(p,'missing') for p in paths})
        self.assertTrue(added)
        recalled=memories.recall('config UTF8','unrelated-new-scope',states)
        self.assertEqual(recalled[0]['applicability'],
                         'target_dependencies_unchanged_external_state_unverified')
        states['config.txt']='file:v2'
        recalled=memories.recall('config UTF8','unrelated-new-scope',states)
        self.assertEqual(recalled[0]['applicability'],
                         'target_dependencies_changed_or_unknown_recheck_required')

    def test_delivery_gap_extracts_outputs_not_command_inputs_and_never_claims_success(self):
        goal='''Use configs/sample.csv as input.\nRequired Output:\n- outputs/report.json\n- notes.md\nRequired Commands:\npython run.py configs/sample.csv'''
        task=TaskSpec('delivery',goal)
        self.assertEqual(requested_artifacts(task),['outputs/report.json','notes.md'])
        env=FakeEnvironment(); env.dependencies['outputs/report.json']='file:v1'
        view=DeliveryProgress(task,env).view()
        self.assertEqual(view['missing_artifacts'],['notes.md'])
        self.assertFalse(view['controller_claims_success'])
        self.assertTrue(all(row['status']=='unverified_by_controller' for row in view['criteria']))

    def test_advisor_invalid_evidence_defers_without_harming_main(self):
        bad=dict(alternatives=[dict(ADVICE['alternatives'][0],evidence_ids=['E999'])])
        result, _, _, _, _, _=self.exercise([run_action('fail')]*3+[SUBMIT],[bad])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['mechanism_utilization']['advisor_deferred'],1)

    def test_advisor_transient_error_defers(self):
        result, _, _, _, _, _=self.exercise([dict(action='consult',question='What next?'),SUBMIT],[ModelCallError('temporary')])
        self.assertTrue(result['submitted'])
        self.assertEqual(result['advisor_rounds'],1)

    def test_request_budget_counts_advisor(self):
        result, _, _, _, env, _=self.exercise([run_action('fail')]*3,[ADVICE],LeanConfig(max_turns=4))
        self.assertEqual(result['interaction_rounds'],4)
        self.assertEqual(result['action_rounds'],3)
        self.assertFalse(result['submitted'])

    def test_rejected_submission_keeps_cumulative_budgets_and_memory(self):
        rejected=[True,False]
        def feedback(artifact):
            return 'Try again' if rejected.pop(0) else None
        result, _, actor, _, _, _=self.exercise([run_action('write','A'),SUBMIT,run_action('write','B'),SUBMIT],feedback=feedback)
        self.assertTrue(result['submitted'])
        self.assertEqual(result['tool_calls'],2)
        self.assertEqual(result['interaction_rounds'],4)
        self.assertIn('Try again',json.dumps(actor.prompts[2]))

    def test_errors_bounded_and_artifact_delivered(self):
        result, _, _, _, _, _=self.exercise([{'action':'invalid'}]*3)
        self.assertEqual(result['stop_reason'],'model_or_protocol_error_limit')
        self.assertIsNotNone(result['artifact'])

    def test_secret_redacted_and_log_tamper_detected(self):
        result, events, _, _, _, runner=self.exercise([run_action('write','fixture-secret-value'),SUBMIT])
        path=runner.output/'events.jsonl'
        self.assertNotIn('fixture-secret-value',path.read_text())
        path.write_text(path.read_text().replace('Create useful output','altered task'))
        with self.assertRaises(ValueError): read_trace(path)

    def test_single_use_and_independent_clients(self):
        result, _, actor, _, env, runner=self.exercise([SUBMIT])
        with self.assertRaises(RuntimeError): runner.run(TaskSpec('other','goal'))
        with self.assertRaises(ValueError): LeanTaskRunner(env,actor,actor,output='unused')

    def test_invalid_configs(self):
        for cfg in ({'wall_seconds':float('nan')},{'max_tools':True},{'max_active_checkpoints':1}):
            with self.assertRaises(ValueError): LeanConfig(**cfg)
        for action in (dict(action='run',argv=['x'],timeout_seconds=-2),dict(action='run',argv=[])):
            with self.assertRaises(ValueError): parse_action(action)

    def test_expired_model_response_cannot_execute_a_command(self):
        clock=[0.0]
        class Late(Scripted):
            def complete_json(self, **kwargs):
                clock[0]=3.0
                return run_action('write','should not run')
        with tempfile.TemporaryDirectory() as tmp, patch('bestfgs.lean_runtime.time.monotonic',side_effect=lambda:clock[0]):
            env=FakeEnvironment()
            result=LeanTaskRunner(env,Late([]),Scripted([]),LeanConfig(wall_seconds=2),Path(tmp)/'audit').run(TaskSpec('t','goal'))
        self.assertEqual(result['stop_reason'],'wall_budget')
        self.assertEqual(env.executed,[])

    def test_auth_failure_stops_dispatch_including_automatic_advisor(self):
        class Denied(Scripted):
            last_failure_detail='http_401'
            last_failure_kind='transport'
            def complete_json(self,**kwargs): raise ModelCallError('denied')
        for role in ('action','advisor'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as tmp:
                env=FakeEnvironment()
                actor=Denied([]) if role=='action' else Scripted([run_action('fail')]*3)
                advisor=Denied([]) if role=='advisor' else Scripted([])
                result=LeanTaskRunner(env,actor,advisor,output=Path(tmp)/'audit').run(TaskSpec('t','goal'))
                self.assertEqual(result['stop_reason'],'credential_or_balance_error')
                self.assertEqual(result['tool_calls'],0 if role=='action' else 3)

    def test_shared_inner_client_rejected_and_wire_repair_is_bounded(self):
        from bestfgs.retrac_adapter import RetracModelConfig
        class Inspect(Scripted):
            config=RetracModelConfig('fixture','http://localhost','fake-value',timeout_seconds=10,max_wall_time_seconds=10)
            def complete_json(self,**kwargs):
                self.seen=self.config
                return SUBMIT
        class Wrapper:
            def __init__(self,inner): self.inner=inner
            def __getattr__(self,name): return getattr(self.inner,name)
        inner=Inspect([])
        with self.assertRaises(ValueError):
            LeanTaskRunner(FakeEnvironment(),Wrapper(inner),Wrapper(inner),output='unused')
        with tempfile.TemporaryDirectory() as tmp:
            runner=LeanTaskRunner(FakeEnvironment(),Wrapper(inner),Scripted([]),LeanConfig(wall_seconds=3),Path(tmp)/'audit')
            runner.run(TaskSpec('t','goal'))
        self.assertEqual(inner.seen.request_attempts,2)
        self.assertLessEqual(inner.seen.max_wall_time_seconds,3)
        self.assertEqual(inner.config.max_wall_time_seconds,10)


@unittest.skipUnless(os.name=='posix','Linux/WSL process and filesystem contract')
class LocalEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        seed=self.root/'seed'; seed.mkdir(); (seed/'data').write_text('original')
        self.env=LiveWorkspace(seed,self.root/'run',credential_variables=['TEST_PRIVATE_KEY'])
    def command(self, code, timeout=4):
        return self.env.execute(run_action(sys.executable,'-c',code,timeout_seconds=timeout),time.monotonic()+timeout)
    def test_real_checkpoint_restore_and_seed_unchanged(self):
        snap=self.env.checkpoint('original')
        self.command("from pathlib import Path; Path('data').write_text('changed')")
        self.env.restore(snap)
        self.assertEqual((self.env.workspace/'data').read_text(),'original')
        self.assertEqual((self.root/'seed/data').read_text(),'original')
        self.assertEqual(next((self.root/'run').glob('retired-*')).joinpath('data').read_text(),'changed')
    def test_dependency_state_tracks_only_requested_files(self):
        first=self.env.dependency_state(['data','missing.txt'])
        self.assertTrue(first['data'].startswith('file:'))
        self.assertEqual(first['missing.txt'],'missing')
        (self.env.workspace/'unrelated').write_text('new')
        self.assertEqual(self.env.dependency_state(['data']),{'data':first['data']})
        (self.env.workspace/'data').write_text('changed')
        self.assertNotEqual(self.env.dependency_state(['data'])['data'],first['data'])
    def test_checkpoint_tampering_refused(self):
        snap=self.env.checkpoint('original')
        (Path(snap['path'])/'data').write_text('tampered')
        with self.assertRaises(RuntimeError): self.env.restore(snap)
    def test_credentials_removed_from_task_environment(self):
        with patch.dict(os.environ,{'TEST_PRIVATE_KEY':'hidden','DEEPSEEK_API_KEY':'hidden'}):
            r=self.command("import os; print(os.getenv('TEST_PRIVATE_KEY'),os.getenv('DEEPSEEK_API_KEY'))")
        self.assertEqual(r.stdout.strip(),'None None')
    def test_cwd_cannot_escape(self):
        r=self.env.execute(dict(action='run',argv=['true'],cwd='..'),time.monotonic()+1)
        self.assertTrue(r.blocked)
    def test_background_descendant_cannot_write_after_command(self):
        code="import subprocess,sys; subprocess.Popen([sys.executable,'-c',\"import time,pathlib; time.sleep(.5); pathlib.Path('late').write_text('bad')\"] )"
        self.command(code)
        time.sleep(.7)
        self.assertFalse((self.env.workspace/'late').exists())
    def test_command_timeout(self):
        r=self.env.execute(run_action(sys.executable,'-c','import time; time.sleep(5)'),time.monotonic()+.1)
        self.assertTrue(r.timed_out)


if __name__=='__main__': unittest.main()
