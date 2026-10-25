"""Verbatim handoff, matched existing infrastructure, zero model requests."""
import json
from pathlib import Path
import shutil
from common import save,sha

ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
BASE=ROOT.parent/'longcli-lats-taco-small20-20261007'
HANDOFF=WORK/'components/recuris-handoff-20261007/recuris'

def main():
    manifest=json.loads((HANDOFF/'HANDOFF_MANIFEST.json').read_text())
    for r in manifest['files']:
        p=HANDOFF.parent/r['path']
        assert p.resolve().is_relative_to(HANDOFF.resolve())
        assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256'],r['path']
    dest=ROOT/'recuris'
    if not dest.exists():shutil.copytree(HANDOFF,dest,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','.test-tmp*'))
    for name in ('client.py','sandbox.py','command_driver.py','safe_process.py','grade_one.py',
                 'grading_adapter.py','grading_worker.py','status.py','launch.py','runner.py','acceptance.py'):
        if not (ROOT/name).exists():shutil.copyfile(BASE/name,ROOT/name)
    p=json.loads((BASE/'protocol.json').read_text())
    for k in ('lats','taco','taco_concurrency'):p.pop(k,None)
    p.update(experiment=ROOT.name,methods=['recuris_frozen'],total_trials=20,
        official_feedback_to_solver=False,attempts_per_task=1,cross_task_memory=False,
        mode='single_pass_fixed_memory',max_actor_steps=800,
        recuris={'seed':'terminal_seed.json','learned_memory':False,'E_W_rho_C_fixed':True,
            'working_state_mutable':True,'meta_agent_enabled':False,'tta_enabled':False,
            'terminal':'same stateless bounded bash command bridge as other arms',
            'public_verification_receipts':'actual bounded command exit, not tmux markers',
            'input_meter':'48000 UTF8 envelope bytes, not handoff default120000 chars'},
        storage_admission_floor=None)
    save(ROOT/'protocol.json',p)
    shutil.copyfile(dest/'src/recuris/skills/terminal_seed.json',ROOT/'terminal_seed.json')
    save(ROOT/'source-provenance.json',{'handoff_archive_sha256':sha(Path('C:/Users/54177/xwechat_files/wxid_5t3x1tx79fan11_b93f/msg/file/2026-10/recuris-handoff.zip')),
        'handoff_files_verified':len(manifest['files']),'paper':'https://arxiv.org/abs/2608.24876',
        'author_reference_commit':'7d3745ab787b1206ccd981cb1511100476097266',
        'handoff_modules_verbatim':True,'shared_infrastructure':{n:sha(ROOT/n) for n in ('client.py','sandbox.py','command_driver.py','safe_process.py','grade_one.py','grading_adapter.py')},
        'experimental_mode_user_choice':'No official feedback; same configuration as other arms'})
    print(json.dumps({'prepared':True,'mode':p['mode'],'paid_model_calls':0,'verified_handoff_files':len(manifest['files'])}))

if __name__=='__main__':main()
