"""Pause new admission on shared faults; never kill healthy sibling tasks."""
import time


def dispatch(protocol, rows, *, spawn, status, admission, heartbeat, watchdog,
             recover_exit, shared_fault=lambda: None, clock=time.time, sleep=time.sleep,
             initial_active=None, initial_done=(), require_pilot=False):
    pending=list(rows);active=dict(initial_active or {});done=list(initial_done);errors=[];fatal=None
    pilot=protocol['tasks'][0]['task'];pilot_done=set()
    def view(terminal=False):
        return dict(state=('needs_attention' if fatal or (terminal and errors) else
                           'generation_complete' if terminal else 'running'),
                    updated=clock(),active=list(active),
                    pending=[r['method']+'--'+r['task'] for r in pending],completed=list(done),
                    errors=list(errors),fatal=fatal,concurrency=protocol['concurrency'],
                    pilot_methods_complete=sorted(pilot_done),controller_state='parallel_no_sibling_kill',
                    pilot_completion_required=require_pilot,source_unchanged=True,
                    concurrency_per_arm=protocol['concurrency_per_arm'])
    while active or (pending and not fatal):
        try:
            fault=shared_fault()
            if fault and not fatal:fatal=fault
        except Exception as error:
            if not fatal:fatal='shared_status_'+type(error).__name__
        for job,(process,row,began) in list(active.items()):
            try:
                live=status(job,False)
                fault=live.get('engineering_fault') or live.get('cleanup_error')
                if fault and not fatal:fatal=fault
                if process.is_alive() and (clock()-live.get('updated',began)>600
                        or clock()-began>protocol['wall_seconds']+120):
                    watchdog(job,process,live)
                    errors.append(dict(job=job,reason='watchdog_timeout'))
                if process.is_alive():continue
                process.join()
                summary=status(job,True)
                if not summary:summary=recover_exit(job,process)
                fault=admission.observe(row['method'],summary,pilot=require_pilot and row['task']==pilot)
                if fault and not fatal:fatal=fault
                if summary.get('task_local_error'):
                    errors.append(dict(job=job,reason=summary['task_local_error']))
                if summary.get('state')=='awaiting_grade':done.append(job)
                else:
                    errors.append(dict(job=job,reason=summary.get('engineering_fault') or
                                       summary.get('stop_reason') or 'missing_summary'))
                if row['task']==pilot and not fault:pilot_done.add(row['method'])
                active.pop(job)
            except Exception as error:
                # Transient malformed/missing status is not permission to kill a sibling.
                # A paused controller still services all owned tasks and watchdogs.
                if not fatal:fatal='task_status_'+type(error).__name__
                if clock()-began>protocol['wall_seconds']+120:
                    watchdog(job,process,{})
                    active.pop(job)
                    errors.append(dict(job=job,reason='unreadable_status_timeout'))
        admitted=True
        while admitted and not fatal and len(active)<protocol['concurrency'] and pending:
            admitted=False
            for i,row in enumerate(pending):
                if require_pilot and len(pilot_done)<len(protocol['methods']) and row['task']!=pilot:continue
                if sum(r['method']==row['method'] for _,r,_ in active.values())>=protocol['concurrency_per_arm']:continue
                job=row['method']+'--'+row['task']
                try:
                    process=spawn(row)
                    active[job]=(process,row,clock());pending.pop(i);admitted=True
                except Exception as error:fatal='spawn_'+type(error).__name__
                break
        heartbeat(view())
        if active or (pending and not fatal):sleep(3)
    result=view(True);heartbeat(result);return result
