"""Explicit operator repair: scoped stop/snapshot and model-free regrading.

Never imports a solver client or reads credentials. Existing attempts stay intact.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time
from common import ROOT,save,sha
from docker_terminal import docker,cleanup_owned
from safe_process import run_bounded


def stop_host_runner():
    # No pgrep/ps scan: unrelated kernel-uninterruptible /proc entries can
    # block the entire scan. Use only this campaign's recorded PID identities.
    health=json.loads((ROOT/'health.json').read_text())
    candidates={health['pid'],*health.get('active_pids',{}).values()}
    for f in (ROOT/'jobs').glob('*/health.json'):
        s=json.loads(f.read_text())
        if s.get('pid'):candidates.add(s['pid'])
    stopped=[]
    for pid in candidates:
        if pid==os.getpid():continue
        f=Path(f'/proc/{pid}/cmdline')
        if not f.exists():continue
        argv=f.read_bytes().split(b'\0')
        if str(ROOT/'runner.py').encode() not in argv:continue
        if f.stat().st_uid!=os.getuid():raise RuntimeError('Refuse foreign owner')
        os.kill(pid,signal.SIGSTOP);os.kill(pid,signal.SIGKILL);stopped.append(pid)
    return stopped


def reconcile():
    assert ROOT.name in ('lizh639-longcli-reflexion20-college-20261006',
                         'lizh639-longcli-retrac20-engineering-repair-20261006')
    backup=ROOT/'before-live-infra-repair-20261006';backup.mkdir(exist_ok=True)
    for name in ('health.json','grading-health.json'):
        f=ROOT/name
        if f.exists() and not (backup/name).exists():shutil.copyfile(f,backup/name)
    h=json.loads((ROOT/'health.json').read_text())
    print(json.dumps({'phase':'stop_recorded_host_workers','model_calls':0}),flush=True)
    host_stops=stop_host_runner()
    # Stop the old pure grader so explicit repair does not race its admissions.
    f=ROOT/'grading-launch.json'
    if f.exists():
        pid=json.loads(f.read_text())['pid'];p=Path(f'/proc/{pid}/cmdline')
        if p.exists() and str(ROOT/'grading_worker.py').encode() in p.read_bytes().split(b'\0'):
            os.kill(pid,signal.SIGKILL)
    h.update(state='needs_attention',updated=time.time(),active=[],
             infrastructure_repair='in_progress',paid_model_restart=False)
    save(ROOT/'health.json',h)
    receipts=[];blocked=[]
    for d in sorted((ROOT/'jobs').glob('*--*')):
        f=d/'container.json'
        if not f.exists():continue
        c=json.loads(f.read_text());name,job=c['name'],c['job']
        print(json.dumps({'phase':'cleanup','job':job,'container':name,'model_calls':0}),flush=True)
        if not (backup/(job+'-summary.json')).exists() and (d/'summary.json').exists():
            shutil.copyfile(d/'summary.json',backup/(job+'-summary.json'))
        try:
            receipt=cleanup_owned(name,job,d/'infra-repaired-app')
            if receipt.get('snapshot'):
                from common import export_tree
                archive=d/'infra-repaired-source.tar.gz'
                if not archive.exists():receipt['artifact']=export_tree(receipt['snapshot'],archive,source_only=True)
            receipt['job']=job;receipts.append(receipt)
            f=d/'summary.json' if (d/'summary.json').exists() else d/'health.json'
            s=json.loads(f.read_text());s.update(task_processes_stopped=True,
                cleanup_repaired_at=time.time(),cleanup_receipt=receipt)
            if s.get('state') in ('preparing','running'):
                s.update(state='batch_interrupted',stop_reason='engineering_batch_halt')
            save(d/'summary.json',s);save(d/'health.json',s)
        except Exception as error:blocked.append({'container':name,'job':job,'error':type(error).__name__})
        print(json.dumps({'phase':'cleanup_progress','job':job,'completed':len(receipts),'blocked':blocked,'model_calls':0}),flush=True)
        h.update(updated=time.time(),cleanup_pending=blocked,cleanup_completed=len(receipts));save(ROOT/'health.json',h)
    # Failed grading containers: only exact names attested in this campaign's
    # original stderr, matching the campaign label and archived source checksum.
    for d in sorted((ROOT/'incoming').glob('*--*')):
        log=d/'grading-stderr.log';summary=d/'summary.json'
        if not log.exists() or not summary.exists():continue
        s=json.loads(summary.read_text());archive=d/'final-source.tar.gz'
        assert sha(archive)==s['artifact']['sha256']
        for name in sorted(set(re.findall(r'longcli-paired10-[0-9a-f]{12}',log.read_text()))):
            try:
                p=docker('inspect',name,'--format','{{json .Config.Labels}}',check=False,seconds=8)
                if p.returncode:
                    if 'no such' in p.stderr.lower():continue
                    raise RuntimeError('Grader absence unconfirmed')
                assert json.loads(p.stdout).get('experiment')==ROOT.name
                state=json.loads(docker('inspect',name,'--format','{{json .State}}',seconds=8).stdout)
                if state['Running']:docker('kill',name,check=False,seconds=10)
                state=json.loads(docker('inspect',name,'--format','{{json .State}}',seconds=8).stdout)
                if state['Running']:raise RuntimeError('Grader still running; keep container')
                # Frozen solver artifact, original grading source and test_output
                # remain on the host; this failed grader has no unique task source.
                docker('rm',name,seconds=10)
                receipts.append({'job':d.name,'container':name,'state':'failed_grader_removed',
                    'source_archive_retained':str(archive),'artifact_sha256':sha(archive)})
            except Exception as error:blocked.append({'container':name,'job':d.name,'error':type(error).__name__})
    h.update(updated=time.time(),infrastructure_repair='cleanup_blocked' if blocked else 'cleanup_complete',
             cleanup_pending=blocked,active=[])
    save(ROOT/'health.json',h)
    save(ROOT/'live-infra-repair.json',{'time':time.time(),'host_stops':host_stops,'receipts':receipts,
        'blocked':blocked,'model_calls':0,'automatic_solver_restart':False})
    print(json.dumps({'state':h['infrastructure_repair'],'reconciled':len(receipts),'blocked':blocked,'model_calls':0}),flush=True)
    return not blocked


def regrade_missing():
    import college_grader as grader
    from grading_adapter import install
    protocol=json.loads((ROOT/'protocol.json').read_text())
    attempt=ROOT/'grading-infra-repair-20261006'
    attempt.mkdir(exist_ok=True)
    for name in ('protocol.json','input-manifest.json'):
        dst=attempt/name
        if not dst.exists():shutil.copyfile(ROOT/name,dst)
        assert sha(dst)==sha(ROOT/name)
    if not (attempt/'upstream').exists():(attempt/'upstream').symlink_to((ROOT/'upstream').resolve(),target_is_directory=True)
    grader.ROOT=attempt
    cleanup=install(grader)
    # Single operator lock across repaired campaigns. Existing solver budgets
    # and fixed official grading resources are not modified.
    import fcntl
    with Path('/var/tmp/lizh639-longcli-grading-infra-repair.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for d in sorted((ROOT/'incoming').glob('*--*')):
            job=d.name;canonical=ROOT/'grades'/job/'result.json'
            if canonical.exists():continue
            summary=json.loads((d/'summary.json').read_text())
            if summary.get('state')!='awaiting_grade':continue
            existing=attempt/'grades'/job
            assert not existing.exists(),'Keep prior repair attempt; do not automatically regrade twice'
            cleanup['errors'].clear()
            save(ROOT/'grading-repair-health.json',{'state':'grading','job':job,'updated':time.time(),'model_calls':0})
            result=grader.grade(job,d/'final-source.tar.gz',summary['artifact']['sha256'])
            result.update(grading_attempt_root=str(attempt),paid_model_calls_for_repair=0,
                          original_failed_attempt_retained=True)
            if cleanup['errors']:result['grading_cleanup_errors']=list(cleanup['errors'])
            if result['grading_state']!='complete':
                save(existing/'result.json',result)
                raise RuntimeError('Repair grading failed; preserve attempt and stop')
            # The score is durable even if removing a stopped grader later fails.
            save(canonical,result)
            try:
                name=result['container']
                assert docker('inspect',name,'--format','{{index .Config.Labels "experiment"}}',seconds=8).stdout.strip()==ROOT.name
                assert docker('inspect',name,'--format','{{.State.Running}}',seconds=8).stdout.strip()=='false'
                docker('rm',name,seconds=10);result['grading_container_destroyed']=True
            except Exception as error:result['grading_cleanup_error']=type(error).__name__
            save(canonical,result)
            if result.get('grading_cleanup_error') or result.get('grading_cleanup_errors'):
                raise RuntimeError('Score retained but cleanup failed; stop grading admission')
            print(json.dumps({'job':job,'f2p':result['f2p'],'model_calls':0}),flush=True)
    reports=[json.loads(p.read_text()) for p in (ROOT/'grades').glob('*/result.json')]
    save(ROOT/'grading-repair-health.json',{'state':'complete_for_available_artifacts',
        'updated':time.time(),'scored':sum(r['grading_state']=='complete' for r in reports),'model_calls':0})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--regrade-missing',action='store_true');args=parser.parse_args()
    try:
        healthy=reconcile()
        if args.regrade_missing and healthy:regrade_missing()
    except Exception as error:
        save(ROOT/'grading-repair-health.json',{'state':'needs_attention','error_type':type(error).__name__,
            'error':str(error)[:400],'updated':time.time(),'model_calls':0})
        raise
