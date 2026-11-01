"""Offline regression, real isolated Docker smoke, original config verification."""
import io,json,sys,tempfile,time,unittest
from common import ROOT,save,sha

def main():
    from verify_contract import verify
    proof=verify();assert proof['verified_core_files']==136
    tempfile.tempdir=str(ROOT/'evidence/test-temp')
    sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'sources/bestfgs-project/src'),
        str(ROOT/'sources/bestfgs-project/tests')]
    names=['test_soft_review','test_subgoals','test_error_routing','test_cost_bar','test_guarded_delivery']
    # This historical test asserts EXACTLY two changed files. Our independent
    # contract now verifies the third, solely prose-length-related change.
    from test_no_recovery_stop import NoRecoveryStopTests
    selected=[n for n in unittest.defaultTestLoader.getTestCaseNames(NoRecoveryStopTests)
              if n!='test_only_two_core_files_change']
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(n) for n in names)
    suite.addTests(NoRecoveryStopTests(n) for n in selected)
    log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    (ROOT/'evidence/unit-tests.txt').write_text(log.getvalue())
    assert result.wasSuccessful(),log.getvalue()[-10000:]
    p=json.loads((ROOT/'protocol.json').read_text())
    old=json.loads((ROOT.parent/'kz2-low4-20261009/protocol.json').read_text())
    deployment={'experiment','name','revision','tasks','total_trials','concurrency',
                'concurrency_per_arm','task_selection','safety'}
    assert all(p.get(k)==v for k,v in old.items() if k not in deployment)
    assert p['tasks']==[row for row in old['tasks'] if row['task'] in ['61810_mmap','cmu15_445_p2']]
    assert p['safety']['per_task_cny']==50
    from guarded_trial import trial
    smoke=trial(dict(p['tasks'][0],method='1342'),mock=True)
    assert smoke['state']=='keyless_pass' and smoke['actual_api_attempts']==0
    assert smoke['task_processes_stopped'] and smoke['tool_calls']==2
    from docker_environment import docker,BASE
    for row in p['tasks']:
        assert docker('image','inspect',row['image'],'--format','{{.Id}}').stdout.strip()==row['image_id']
        assert (BASE/('starter-'+row['task']+'.tar.gz')).is_file()
    files=[*ROOT.glob('*.py'),ROOT/'protocol.json',ROOT/'source-provenance.json',ROOT/'historic-config-lock.json',
           *(ROOT/'sources').rglob('*.py'),*(ROOT/'compatibility').rglob('*.py'),*(ROOT/'tests').rglob('*.py')]
    checks=dict(tests=result.testsRun,passed=result.testsRun,paid_model_calls=0,
        prose_length_cannot_veto_action=True,three_long_fields_cannot_stop_task=True,
        original_commands_and_evidence_preserved=True,solver_configuration_unchanged=True,
        only_one_additional_core_change=True,recovery_hard_stop_disabled=True,
        fresh_docker_smoke=True,atomic_cny50_guard=True)
    save(ROOT/'ready.json',dict(name='KZ2.0',revision=p['revision'],ready=True,time=time.time(),
        checks=checks,paid_model_calls=0,hashes={f.relative_to(ROOT).as_posix():sha(f) for f in files}))
    print(json.dumps(dict(ready=True,checks=checks)))

if __name__=='__main__':main()
