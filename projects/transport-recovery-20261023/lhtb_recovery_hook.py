from pathlib import Path
import asyncio,hashlib,json,shutil,time,subprocess,os
ROOT=Path(__file__).absolute().parent

def read(p):return json.loads(p.read_text())
def actions_from(trial):
    actions=[]
    for file in sorted(trial.glob('agent/phase-*/dsh.jsonl')):
        complete={}
        for session in file.parent.glob('dsh-home/sessions/*/session-*/session.v4.jsonl.zstd'):
            raw=subprocess.check_output(['zstd','-dc',str(session)])
            for line in raw.splitlines():
                event=json.loads(line)
                if event.get('type')=='tool/call':
                    data=event['data'];complete[data['callId']]=json.loads(data['arguments'])
        events=[]
        for line in file.read_text().splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        results={e['callId']:e for e in events if e.get('type')=='tool_result'}
        for e in events:
            if e.get('type')!='tool_call' or e.get('tool') not in ('write','edit','bash'):continue
            result=results.get(e['callId'])
            if result is None:continue
            text=str(result.get('result',''))
            if '"executed":false' in text.replace(' ','') or 'semantic_reconnaissance_required' in text:continue
            if e['tool'] in ('write','edit') and result.get('status')!='completed':continue
            value=complete.get(e['callId'])
            assert value is not None,'Missing untruncated original tool input'
            actions.append(dict(tool=e['tool'],input=value,callId=e['callId']))
    return actions

async def restore(agent,env):
    job=os.environ.get('RECOVERY_ACCEPTANCE_JOB') or os.environ.get('CAMPAIGN_BUDGET_JOB');rows=read(ROOT/'recovery-rows.json')
    row=next((r for r in rows if r['job']==job),None)
    if not row or not row.get('source_trial'):return
    trial=Path(row['source_trial']);usage=(row.get('result') or {}).get('shared_usage') or {}
    live=agent.logs_dir/'live';live.mkdir(exist_ok=True)
    if usage:
        usage=dict(usage);usage['stopped']=None
        (live/'shared-state.json').write_text(json.dumps(usage))
    if not row.get('restore_progress'):return
    actions=actions_from(trial)
    await env.upload_file(ROOT/'upstream/tasks'/row['task']/'instruction.md',agent.cwd+'/BENCHMARK_INSTRUCTION.md')
    local=agent.logs_dir.parent/'operator-recovery-actions.json';local.write_text(json.dumps(actions))
    await env.upload_file((ROOT/'replay_tools.py').resolve(),'/installed-agent/replay_tools.py')
    await env.upload_file(local,'/installed-agent/recovery-actions.json')
    result=await env.exec('/opt/kz-python/bin/python3 /installed-agent/replay_tools.py /installed-agent/recovery-actions.json',cwd=agent.cwd,user=env.default_user,timeout_sec=3600)
    (agent.logs_dir.parent/'operator-recovery-replay.json').write_text(result.stdout or '{}')
    if result.return_code:raise RuntimeError('Historical tool replay did not restore safely; no model call admitted')
    await agent.exec_as_root(env,'rm -f /installed-agent/recovery-actions.json /installed-agent/replay_tools.py',timeout_sec=30)
    phases=sorted(trial.glob('agent/phase-*'))
    phases=[p for p in phases if list((p/'dsh-home/sessions').glob('*/session-*/session.v4.jsonl.zstd'))]
    assert phases,'Missing original session'
    previous=phases[-1];new=agent.logs_dir/previous.name;new.mkdir(exist_ok=True)
    agent.phase=int(previous.name.split('-')[1]);agent.recovery_initial_phase=agent.phase
    for folder in ['dsh-home','kz','recuris']:
        if (previous/folder).exists():shutil.copytree(previous/folder,new/folder,symlinks=True)
    sessions=list((new/'dsh-home/sessions').glob('*/session-*/session.v4.jsonl.zstd'));assert len(sessions)==1
    agent.resume_session=sessions[0].parent.name
    session_events=[json.loads(line) for line in subprocess.check_output(['zstd','-dc',str(sessions[0])]).splitlines()]
    original_user=next(e for e in session_events if e.get('type')=='user/message')
    agent.recovery_instruction='\n'.join(b['text'] for b in original_user['data']['content'] if b['type']=='text')
    agent.recovery_remaining=row['remaining_seconds']
    for statefile in (new/'kz').glob('*.json'):
        state=read(statefile)
        if isinstance(state.get('full'),dict) and 'startedAt' in state['full']:
            expected=state['full'].get('taskInstruction',{}).get('sha256')
            if state.get('session')==agent.resume_session and expected:
                assert hashlib.sha256(agent.recovery_instruction.encode()).hexdigest()==expected,'Original task instruction fingerprint differs'
            state['full']['startedAt']=int(time.time()*1000)-(10800-row['remaining_seconds'])*1000
            statefile.write_text(json.dumps(state))
    (agent.logs_dir.parent/'operator-recovery.json').write_text(json.dumps(dict(source_trial=str(trial),restored_actions=len(actions),session=agent.resume_session,
        remaining_seconds=row['remaining_seconds'],original_budget_job=job,model_calls=0),indent=2))

async def snapshot(trial):
    if os.environ.get('LHTB_OFFLINE')=='1':return
    env=trial._environment
    result=await env._run_docker_compose_command(['ps','-a','-q','main'],check=True,timeout_sec=30)
    ids=(result.stdout or '').split();assert len(ids)==1
    folder=trial._trial_paths.trial_dir;phase=len(list(folder.glob('submission-snapshot-*.json')))
    tag='lhtb-recovery-snapshot:'+os.environ['PAIRED_ATTEMPT_ID']+'-'+str(phase)
    proc=await asyncio.create_subprocess_exec('docker','commit',ids[0],tag,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    output,error=await proc.communicate()
    if proc.returncode:raise RuntimeError('Snapshot failed; completed container must be retained')
    (folder/f'submission-snapshot-{phase:04d}.json').write_text(json.dumps(dict(image_id=output.decode().strip(),tag=tag,container_id=ids[0],before_verifier=True),indent=2))
