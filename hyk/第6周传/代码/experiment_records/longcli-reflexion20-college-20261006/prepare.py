"""Public source and input checks, real Docker/tmux keyless acceptance, seal."""
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import time
from common import ROOT,save,sha
from docker_terminal import BASE,docker,cleanup_owned

def main(revision=1):
    assert not (ROOT/'launch.claim').exists()
    old=json.loads((BASE/'protocol.json').read_text())
    p={k:old[k] for k in ('commit','tasks','base_images','model','thinking','temperature','grading_resources')}
    p.update(experiment=ROOT.name,methods=['reflexion'],total_trials=20,max_turns=800,max_tools=600,
        max_tokens=4096,input_bytes=48000,output_bytes=24000,command_seconds=300,wire_attempt_ceiling=1600,
        retries_per_decision=1,max_trials=3,max_steps_per_trial=40,memory_size=3,repeat_action_limit=4,max_parse_attempts=2,
        context_reserve_bytes=12000,max_reflection_chars=4000,automatic_task_retry=False,
        generation_resources={'concurrency_total':4,'cpu_affinity_each':2,'cpusets':[[24,25],[26,27],[28,29],[30,31]],
                              'address_space_gib_per_process':3,'aggregate_memory_limit':None},
        source_archive_sha256='a0dc4e333eabe9e583b6471ebc5dec15c58a441c00b7dd25a69549e8172f90fd',
        source='User reflexion-handoff(1).zip independent paper implementation; not author-official code',core_unchanged=True,
        interface_note='Academy compute Docker; pinned official TmuxSession + handed-off TmuxTerminal. Fresh task container/HOME, persistent shell across three internal trials. No shared memory across tasks.',
        differences=['Physical host/CPU and Docker PID/proc namespace differ from Cube.',
                     'Per-process AS3GiB is matched; no Cube16GB aggregate parent-container cap.',
                     '48k UTF8 JSON messages; Reflexion has no function schemas. Historical DH counted characters, DSH includes schemas.',
                     'Native algorithm caps3 internal trials x40 Actor steps; external shared budgets are ceilings, not equal actual usage. Internal Evaluator pass is not an official grade.',
                     'Native nonblocking tmux duration caps waiting, not subprocess lifetime; entire sandbox is stopped at task end/deadline.'],
        budget_adapter='Reflexion transport adaptation; all roles and repairs share800 logical requests.',
        endpoint='https://api.deepseek.com',grading='One immutable final source artifact, unchanged official grader, no online hidden feedback')
    p['budget_adapter']=('UTF8/JSON-byte-aware explicit head-tail evidence clipping and review sizing; '
                         'small-JSON Actor hint and short-reflection hint. Original engine/client/prompts source stay sealed; '
                         '3x40/FIFO3/Actor-Evaluator-Reflection and two format attempts unchanged. '
                         'All roles/repairs share800 calls. No hidden tests in internal evaluation.')
    p['engineering_guard']={'fatal_first_task_stops_entire_batch':True,
        'active_fault_poll_seconds':2,'interrupt_other_active_tasks':True,
        'canary_tasks':['cs61_fa24_hog','61810_util'],'canary_concurrency':2,
        'promote_to_concurrency':4,'require_reflection_or_healthy_first_trial_evaluator_pass':True,
        'gpt_monitoring_calls':0,'automatic_failed_task_retry':False}
    p['workspace_transport']='Fresh no-copy app volume; pinned public source tar owns uid/gid0; nested write preflight before any paid request. No added sandbox capabilities.'
    if (ROOT/'protocol.json').exists():assert json.loads((ROOT/'protocol.json').read_text())==p
    else:save(ROOT/'protocol.json',p)
    previous=Path('/var/tmp/lizh639-longcli-dsh20-repair2-20261005')
    if not (ROOT/'upstream').exists():(ROOT/'upstream').symlink_to((previous/'upstream').resolve(),target_is_directory=True)
    for f in ('college_grader.py','input-manifest.json'):
        if not (ROOT/f).exists():shutil.copyfile(previous/f,ROOT/f)
    (ROOT/'incoming').mkdir(exist_ok=True)
    save(ROOT/'grading-ready.json',{'ready':True,'paid_api_requests':0,'grader_sha256':sha(ROOT/'college_grader.py'),
                                   'historical_grader_sha256':sha(previous/'college_grader.py')})
    for line in (ROOT/'reflexion/MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split(None,1);name=name.lstrip('*');f=(ROOT/'reflexion'/name).resolve()
        assert f.is_relative_to((ROOT/'reflexion').resolve()) and sha(f)==digest
    for family,image in p['base_images'].items():
        assert docker('image','inspect',image['tag'],'--format','{{.Id}}').stdout.strip()==image['id']
    manifest=json.loads((BASE/'public-input-manifest.json').read_text())
    for name,digest in manifest['files'].items():assert sha(BASE/name)==digest
    receipts=[]
    from runner import run_trial
    for family in p['base_images']:
        row=next(r for r in p['tasks'] if r['family']==family)
        for pressure in (False,True):
            suffix=f'-docker-r{revision}-'+('pressure' if pressure else 'basic')
            ctx=multiprocessing.get_context('fork');proc=ctx.Process(target=run_trial,args=(row,[24,25],None,True,pressure,suffix))
            proc.start();proc.join(600)
            directory=ROOT/'acceptance-jobs'/('keyless--'+row['task']+suffix)
            if proc.is_alive():
                import signal
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                proc.join(10)
                if proc.is_alive():proc.kill();proc.join(10)
                if (directory/'container.json').exists():
                    c=json.loads((directory/'container.json').read_text());cleanup_owned(c['name'],c['job'])
                raise RuntimeError('Keyless fixture deadline; no paid launch')
            receipt=json.loads((directory/'summary.json').read_text());receipts.append(receipt)
            print(json.dumps({'fixture':receipt['job'],'state':receipt['state'],'error':receipt.get('error')}),flush=True)
    record={'state':'passed' if all(r['state']=='keyless_pass' for r in receipts) else 'failed',
            'paid_api_requests':0,'revision':revision,'trials':receipts}
    save(ROOT/f'docker-acceptance-r{revision}.json',record)
    if all(r['state']=='keyless_pass' for r in receipts):save(ROOT/'docker-acceptance.json',record)
    assert all(r['state']=='keyless_pass' for r in receipts),'Native Docker acceptance failed; no paid launch'
    # Exercise the parent cleanup branch, not only the ordinary engine close.
    from docker_terminal import PersistentTerminal
    d=ROOT/'acceptance-jobs'/f'parent-rescue-r{revision}';d.mkdir()
    terminal=PersistentTerminal(p['tasks'][0],d,[24,25],None,f'parent-rescue-r{revision}')
    try:
        terminal.observe();terminal.execute("printf 'RESCUE_OK\\n' > /app/rescue-proof.txt\n",1)
        cleanup_owned(terminal.name,terminal.job,d/'rescued-app');terminal.closed=True
        assert (d/'rescued-app/rescue-proof.txt').read_text().strip()=='RESCUE_OK'
        assert docker('inspect',terminal.name,check=False).returncode!=0
        save(ROOT/'rescue-acceptance.json',{'state':'passed','paid_api_requests':0,'revision':revision,
                                           'source_retained':True,'owned_container_removed':True})
    finally:
        if not terminal.closed:cleanup_owned(terminal.name,terminal.job,d/'rescued-app')
        if hasattr(terminal,'client'):terminal.client.close()
    import subprocess,sys
    subprocess.run([sys.executable,'-B',str(ROOT/'accept_grading.py')],check=True,timeout=600)
    names=[f.name for f in ROOT.iterdir() if f.suffix in ('.py','.ps1')]+['protocol.json','original-tests.json','adapter-tests.json','docker-acceptance.json','grading-acceptance.json','rescue-acceptance.json','grading-ready.json','input-manifest.json']
    names += [f.relative_to(ROOT).as_posix() for f in (ROOT/'reflexion').rglob('*') if f.is_file() and '__pycache__' not in f.parts and '.pytest_cache' not in f.parts]
    hashes={n:sha(ROOT/n) for n in names}
    # Inputs cannot change between unpaid acceptance and hidden-key launch.
    hashes.update({str(BASE/name):digest for name,digest in manifest['files'].items()})
    hashes[str(BASE/'public-input-manifest.json')]=sha(BASE/'public-input-manifest.json')
    save(ROOT/'ready.json',{'ready':True,'paid_api_requests':0,'hashes':hashes})
    print(json.dumps({'state':'accepted_not_started','paid_api_requests':0}),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--revision',type=int,default=1)
    main(parser.parse_args().revision)
