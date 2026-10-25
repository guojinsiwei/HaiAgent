"""Prepare random reserves, freeze a new complete cohort, then optionally start BOTH arms.

Old task lists/environments/results remain untouched. Never selects by solver result.
Only --start-comparison permits paid inference, after all 100 environments pass checks.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal

from benchmark_runtime import atomic_write_json, atomic_write_text, canonical_sha256, implementation_sha256
from run_notebook import run_lock
import run_comparison
from swe_batch import ROOT, load_plan, prepare_task
from build_swe_reserve import env_key


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def available(root, plan):
    result = {}
    for task in plan['tasks']:
        identity = task['instance_id']
        directory = root / 'prepared' / identity
        state = root / 'states' / (identity + '.json')
        if not state.is_file() or read_json(state).get('status') != 'prepared':
            continue
        if not (directory/'ready.json').is_file() or not (directory/'pip-freeze.txt').is_file():
            continue
        data = read_json(directory/'ready.json')
        if (data['id'] != identity or data['recipe_sha256'] != canonical_sha256(task)
                or data['base_commit'] != task['base_commit'] or data['goal'] != task['problem_statement']):
            raise ValueError(f'Prepared manifest mismatch: {identity}')
        result[identity] = directory
    return result


def choose_tasks(original, reserves, old_ready, new_ready):
    kept = [t for t in original['tasks'] if t['instance_id'] in old_ready]
    needed = original['count'] - len(kept)
    additions = [t for t in reserves['tasks'] if t['instance_id'] in new_ready][:needed]
    if len(kept) + len(additions) != original['count']:
        raise ValueError('Not enough prepared tasks; never shrink denominator')
    iterator = iter(additions)
    final = [t if t['instance_id'] in old_ready else next(iterator) for t in original['tasks']]
    if len({t['instance_id'] for t in final}) != original['count']:
        raise ValueError('Duplicate replacement task')
    replacements = [{'removed':old['instance_id'],'added':new['instance_id'],'reason':'environment_preparation_not_ready'}
                    for old,new in zip(original['tasks'],final) if old['instance_id'] != new['instance_id']]
    return final, replacements


def freeze(args, original, reserves):
    frozen = args.root/'frozen'
    plan_path = frozen/'task-plan.json'
    if plan_path.exists():
        return load_plan(plan_path), frozen
    old_ready = available(args.source_root,original)
    new_ready = available(args.root,reserves)
    tasks, changes = choose_tasks(original,reserves,old_ready,new_ready)
    audit = []
    for change in changes:
        state_path = args.source_root/'states'/(change['removed']+'.json')
        audit.append({**change,'source_preparation_state':read_json(state_path)})
    plan = {k:v for k,v in original.items() if k not in {'plan_sha256','tasks','purpose','eligible_pool_sha256'}}
    plan.update(tasks=tasks, purpose='paired_environment_feasible_development_cohort',
                original_plan_sha256=original['plan_sha256'],reserve_plan_sha256=reserves['plan_sha256'],
                replacement_seed=reserves['sample_seed'],replacement_policy='retain ready originals; take first ready reserves in frozen random order; no solver outcomes',
                replacements=changes, frozen_at=datetime.now(timezone.utc).isoformat())
    plan['plan_sha256'] = canonical_sha256(plan)
    for task in tasks:
        identity = task['instance_id']
        source = old_ready.get(identity) or new_ready[identity]
        target = frozen/'prepared'/identity
        # Copy only small manifests; seed/runtime absolute paths remain provenance-linked.
        atomic_write_json(target/'ready.json', read_json(source/'ready.json'))
        atomic_write_text(target/'pip-freeze.txt',(source/'pip-freeze.txt').read_text(encoding='utf-8'))
    atomic_write_json(frozen/'replacement-audit.json',audit)
    atomic_write_json(frozen/'cohort-summary.json',{'count':len(tasks),'replacements':len(changes),
                      'repos':dict(Counter(t['repo'] for t in tasks)), 'plan_sha256':plan['plan_sha256'],
                      'limitation':'Conditioned on environment preparation success; not an unfiltered random SWE-bench sample'})
    # The existence of this file is the atomic cohort commit marker.
    atomic_write_json(plan_path,plan)
    load_plan(plan_path)
    return plan, frozen


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--source-plan',type=Path,default=ROOT/'examples/swe100-plan.json')
    parser.add_argument('--reserve-plan',type=Path,required=True)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--conda',default='/root/miniconda3/bin/conda')
    parser.add_argument('--prepare-timeout',type=int,default=900)
    parser.add_argument('--deadline',required=True,help='Timezone-aware ISO time; no inference starts at/after it')
    parser.add_argument('--start-comparison',action='store_true')
    args=parser.parse_args(argv)
    args.prepare_fetch_attempts=3
    for name in ('root','source_root','output_root'):
        setattr(args,name,getattr(args,name).resolve())
    for a,b in ((args.root,args.source_root),(args.root,args.output_root),(args.source_root,args.output_root)):
        if a==b or a in b.parents or b in a.parents:
            raise ValueError('Use three disjoint dedicated directories')
    if args.root==Path(args.root.anchor) or args.root==ROOT or args.root in ROOT.parents or ROOT in args.root.parents:
        raise ValueError('Use a dedicated root outside the project')
    deadline=datetime.fromisoformat(args.deadline)
    if deadline.tzinfo is None or args.prepare_timeout<=0:
        raise ValueError('Require aware deadline and positive timeout')
    def check_time():
        if datetime.now(timezone.utc)>=deadline:
            raise ValueError('Deadline reached: no new paid run started')
    check_time()
    if args.start_comparison and not os.getenv('DEEPSEEK_API_KEY'):
        raise ValueError('Configure DEEPSEEK_API_KEY in the launch environment before enabling automatic paid start')
    original,reserves=load_plan(args.source_plan),load_plan(args.reserve_plan)
    if reserves.get('source_plan_sha256')!=original['plan_sha256']:
        raise ValueError('Wrong reserve source plan')
    if {t['instance_id'] for t in original['tasks']} & {t['instance_id'] for t in reserves['tasks']}:
        raise ValueError('Reserve overlaps original')
    with run_lock(args.root):
        config={'original_plan_sha256':original['plan_sha256'],'reserve_plan_sha256':reserves['plan_sha256'],
                'implementation_sha256':implementation_sha256(ROOT),'deadline':args.deadline,
                'output_root':str(args.output_root),'source_root':str(args.source_root),
                'start_comparison':args.start_comparison,'prepare_timeout':args.prepare_timeout}
        lock=args.root/'launch-config.json'
        if lock.exists() and read_json(lock)!=config:
            raise ValueError('Launch config changed; preserve this root')
        atomic_write_json(lock,config)
        if not (args.root/'frozen/task-plan.json').exists():
            for index,task in enumerate(reserves['tasks'],1):
                check_time()
                old_ready=available(args.source_root,original)
                new_ready=available(args.root,reserves)
                if len(old_ready)+len(new_ready)>=original['count']:
                    break
                identity=task['instance_id']
                state_path=args.root/'states'/(identity+'.json')
                if state_path.exists():
                    continue  # no automatic reattempt / best-of selection
                key=env_key(task)
                marker=args.source_root/'base-envs'/(key+'.ready.json')
                if not marker.is_file():
                    raise ValueError('Frozen reserve requires an existing dependency cache')
                atomic_write_json(args.root/'base-envs'/marker.name,read_json(marker))
                atomic_write_json(state_path,{'id':identity,'status':'preparing'})
                print(f'[reserve {index}/{len(reserves["tasks"])}] {identity}; ready originals={len(old_ready)}, reserves={len(new_ready)}',flush=True)
                try:
                    prepare_task(task,args)
                    state={'id':identity,'status':'prepared'}
                except KeyboardInterrupt:
                    atomic_write_json(state_path,{'id':identity,'status':'prepare_error','error':'Interrupted; artifacts retained'})
                    raise
                except Exception as exc:
                    state={'id':identity,'status':'prepare_error','error':str(exc)}
                atomic_write_json(state_path,state)
                print('[reserve result] '+identity+': '+state['status'],flush=True)
        plan,frozen=freeze(args,original,reserves)
        print('[frozen] '+json.dumps({'count':plan['count'],'replacements':len(plan['replacements']),
                                    'plan_sha256':plan['plan_sha256'],'path':str(frozen/'task-plan.json')}),flush=True)
        common=['--plan',str(frozen/'task-plan.json'),'--prepared-root',str(frozen),'--output-root',str(args.output_root)]
        if run_comparison.main(['plan',*common])!=0:
            raise ValueError('Final preflight missing environments')
        # Check every shared runtime before consuming the first token.
        for i,task in enumerate(plan['tasks'],1):
            check_time()
            directory=frozen/'prepared'/task['instance_id']
            ready=read_json(directory/'ready.json')
            run_comparison.check_prepared(ready,{'seed_sha256':ready['seed_sha256'],
                'pip_freeze_sha256':hashlib.sha256((directory/'pip-freeze.txt').read_bytes()).hexdigest()})
            if i%10==0:
                print(f'[preflight] {i}/{len(plan["tasks"])} environments verified',flush=True)
        if not args.start_comparison:
            return 0
        check_time()
        if not os.getenv('DEEPSEEK_API_KEY'):
            raise ValueError('DEEPSEEK_API_KEY missing; preparation complete, no paid calls started')
        print('[comparison launch] '+datetime.now(timezone.utc).isoformat(),flush=True)
        atomic_write_json(args.root/'inference-start.json',{'time':datetime.now(timezone.utc).isoformat(),
                          'plan_sha256':plan['plan_sha256'],'methods':['bestfgs','raw'],'task_attempts':2*plan['count']})
        return run_comparison.main(['run',*common])


if __name__=='__main__':
    def stop(signum,frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
