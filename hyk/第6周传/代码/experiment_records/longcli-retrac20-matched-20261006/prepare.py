"""Unpaid native acceptance; never alter an already launched experiment."""
import argparse
import hashlib
import json
import multiprocessing
from pathlib import Path
from common import ROOT,save,sha


def prepare(worker,revision):
    assert not list(ROOT.glob('launch-*.claim'))
    from runner import BASE
    old=json.loads((BASE/'protocol.json').read_text())
    protocol={k:old[k] for k in ('commit','tasks','model','thinking','temperature','grading_resources','generation_resources')}
    protocol.update(experiment=ROOT.name,methods=['retrac'],total_trials=20,max_turns=800,max_tools=600,
        max_tokens=4096,input_bytes=48000,output_bytes=24000,command_seconds=300,wire_attempt_ceiling=1600,
        retries_per_decision=1,rounds=8,max_steps_per_round=50,summary_variant='full',max_parse_attempts=2,
        compression_reserve_bytes=12000,max_state_chars=8000,automatic_task_retry=False,
        source_archive_sha256='abce18298d86989975885209621b767da29b416c866e7b3233d687475f31a50e',
        source='Desktop retrac-handoff.zip independent paper implementation; not author-official code',
        core_unchanged=True,wait_for_campaign='longcli-dsh20-matched-summary-budget-20261005',
        interface_note='Persistent PTY replaces Docker/tmux on Cube; same original engine, prompts and client. Both rollouts and shell persist per task; task roots reset between tasks.',
        input_note='UTF-8 JSON messages <=48000; no function tool schemas in RE-TRAC JSON protocol. Historical DH counted characters; DSH counts native schema bytes. Not identical token budgets.',
        budget_adapter='Byte-aware size/observation methods only; no hidden history pruning, no solver/summary prompt change. All compression/format repairs share800 logical requests.')
    existing=ROOT/'protocol.json'
    if existing.exists():assert json.loads(existing.read_text())==protocol
    else:save(existing,protocol)
    # Verify the entire handed-off manifest before accepting adapter behavior.
    for line in (ROOT/'retrac/MANIFEST.sha256').read_text().splitlines():
        digest,name=line.split(None,1);name=name.lstrip('*')
        p=(ROOT/'retrac'/name).resolve()
        assert p.is_relative_to((ROOT/'retrac').resolve()) and sha(p)==digest
    resources=json.loads((BASE/f'resources-{worker}.json').read_text())
    receipts=[]
    for pressure in (False,True):
        suffix=f'-w{worker}-r{revision}-'+('pressure' if pressure else 'basic')
        ctx=multiprocessing.get_context('fork')
        from runner import run_trial
        p=ctx.Process(target=run_trial,args=(old['tasks'][0],resources['cpu_slots'][0],None,True,pressure,suffix))
        p.start();p.join(900)
        assert not p.is_alive(),'Acceptance exceeded bounded preparation/execution time'
        path=ROOT/'acceptance-jobs'/('keyless--'+old['tasks'][0]['task']+suffix)/'summary.json'
        receipts.append(json.loads(path.read_text()))
    name=f'acceptance-{worker}-r{revision}.json'
    assert not (ROOT/name).exists()
    passed=all(r['state']=='keyless_pass' for r in receipts)
    save(ROOT/name,{'state':'passed' if passed else 'failed','worker':worker,'trials':receipts,'paid_api_requests':0})
    assert passed, json.dumps(receipts)
    names=['protocol.json','runner.py','matched_adapter.py','chroot_entry.py','pty_terminal.py','context_limit.py',
        'device_setup.py','common.py','launch.py','check_ready.py','prepare.py','original-tests.json','adapter-tests.json',name]
    names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'retrac').rglob('*') if p.is_file()
        and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
    save(ROOT/f'ready-{worker}.json',{'ready':True,'worker':worker,'paid_api_requests':0,
        'acceptance_file':name,'hashes':{n:sha(ROOT/n) for n in names}})
    print(json.dumps({'state':'accepted_not_started','worker':worker,'paid_api_requests':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',type=int,required=True)
    parser.add_argument('--revision',type=int,default=1);args=parser.parse_args();prepare(args.worker,args.revision)
