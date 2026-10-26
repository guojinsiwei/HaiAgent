"""Assemble a fresh small-budget 20-task arm from the frozen 1342 source."""
from pathlib import Path
import json,hashlib,shutil,tarfile,sys
ROOT=Path(__file__).resolve().parent
RELEASE=ROOT.parents[1]/'releases/DH-tools-context-repair-v1'
BASE=ROOT.parent/'longcli-dh-large20-20261007'
def main():
    mail=ROOT.parents[1]/'components/experiment-notifications'
    for name in ('experiment_mail.py','notification-policy.json'):
        shutil.copyfile(mail/name,ROOT/name)
    for name in ('sources','tests'):
        if (ROOT/name).exists():
            assert '--package-only' in sys.argv and not (ROOT/'launch.claim').exists()
            continue
        shutil.copytree(RELEASE/name,ROOT/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.pytest_cache'))
    p=json.loads((BASE/'protocol.json').read_text())
    p.update(experiment=ROOT.name,methods=['dh_tools'],total_trials=20,concurrency=10,
        concurrency_per_arm=10,max_tokens=4096,max_input_bytes=48000,context_limit=46000,
        context_tokens=None,context_headroom_tokens=None,subgoals_enabled=True,
        source='DH 1342 plus three code tools with byte-budget context repair',
        role_output_tokens={r:4096 for r in ('action','advisor','monitor','critic')},
        arms={'dh_tools':{'local_correction':True,'reconnaissance':True,'critic':True,'backtracking':True}},
        tool_names=['inspect_code','edit_code','verify_goal'],budget_profile='small',
        context_meter='serialized UTF8 messages, 48000 bytes hard ceiling; history budget 46000 bytes',
        actual_api_attempts_per_task=800,max_turns=800,max_tools=600,wall_seconds=7200,
        note='Each auxiliary request and tool shares the task limits. No cross-task memory or official feedback.',
        selection='All fixed original LongCLIBench 20 tasks, including cow and lock; fresh attempts',
        comparison='New small-budget tool arm; historical large-budget results are not a controlled ablation')
    p['notifications']={'recipient':'5417779@qq.com','backend':'standalone SMTP watcher, no model calls',
        'events':['completed_with_grading','terminated','heartbeat_stale'],
        'activation':'fresh secure SMTP authorization required'}
    p.pop('matched_dsh',None)
    (ROOT/'protocol.json').write_text(json.dumps(p,indent=2),encoding='utf-8')
    hashes={f.relative_to(ROOT).as_posix():hashlib.sha256(f.read_bytes()).hexdigest()
            for top in ('sources','compatibility') for f in (ROOT/top).rglob('*.py')}
    (ROOT/'source-provenance.json').write_text(json.dumps({'release':'DH-tools-context-repair-v1','base_arm':'1342',
        'hashes':hashes},indent=2),encoding='utf-8')
    allowed={'.py','.json','.txt','.toml','.ps1','.md','.yaml','.yml'};added=[]
    with tarfile.open(ROOT/'deployment.tar.gz','w:gz') as out:
        for f in ROOT.rglob('*'):
            if not f.is_file() or f.suffix not in allowed:continue
            rel=f.relative_to(ROOT)
            if any(x in {'.git','__pycache__','.pytest_cache','.venv','test-deps'} for x in rel.parts):continue
            if rel.parts[0] not in {'sources','compatibility','tests','evidence'} and len(rel.parts)>1:continue
            if rel.parts[0]=='evidence' and f.name!='previous-rejected-candidates.json':continue
            if any(x in f.name.lower() for x in ('.env','credential','private_key')):continue
            out.add(f,arcname=rel.as_posix());added.append(rel.as_posix())
    print(json.dumps({'files':len(added),'trials':len(p['tasks']),'budget':p['budget_profile'],
        'sha256':hashlib.sha256((ROOT/'deployment.tar.gz').read_bytes()).hexdigest()}))
if __name__=='__main__':main()
