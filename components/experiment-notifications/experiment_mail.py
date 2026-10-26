"""No-LLM experiment lifecycle mailer. Secrets arrive only on encrypted stdin."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

RECIPIENT='5417779@qq.com'

def read(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):return {}

def save(path,value):
    p=Path(path);tmp=p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,p)

def public_code(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',value) else 'unspecified'

def alive(pid):
    if type(pid) is not int or pid<=0:return False
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False
    except PermissionError:return True

def event(root,now=None):
    """Public status only; no credentials, logs, environment or model content."""
    root=Path(root);now=time.time() if now is None else now
    h=read(root/'health.json');g=read(root/'grading-health.json')
    p=read(root/'protocol.json');expected=p.get('total_trials')
    if h.get('state')=='needs_attention' or g.get('errors'):
        return {'kind':'terminated','reason':public_code(h.get('fatal') or 'grading_failure'),
            'finished':len(h.get('completed',[])),'scored':g.get('scored',0),'expected':expected}
    if h.get('state')=='generation_complete':
        if g.get('state')!='complete_for_available_artifacts':return None
        n=g.get('scored',0)
        if n!=expected:return {'kind':'terminated','reason':'incomplete_grades',
            'finished':len(h.get('completed',[])),'scored':n,'expected':expected}
        scores=[]
        for f in (root/'grades').glob('*/result.json'):
            r=read(f)
            if r.get('grading_state')=='complete' and type(r.get('score')) in (int,float):scores.append(r['score'])
        return {'kind':'completed','reason':'all_tasks_and_grades_complete','finished':len(h.get('completed',[])),
            'scored':n,'expected':expected,'mean_score':sum(scores)/len(scores) if len(scores)==expected else None}
    if h.get('state')=='running' and now-h.get('updated',now)>600:
        return {'kind':'terminated' if not alive(h.get('pid')) else 'stalled',
            'reason':'worker_missing' if not alive(h.get('pid')) else 'heartbeat_stale_not_confirmed_stopped',
            'finished':len(h.get('completed',[])),'scored':g.get('scored',0),'expected':expected}
    return None

def message(root,notice,sender):
    labels={'completed':'实验结束（评分已完成）','terminated':'实验异常终止','stalled':'实验心跳停更（未确认停止）'}
    m=EmailMessage();m['From']=sender;m['To']=RECIPIENT
    m['Subject']=labels[notice['kind']]+'：'+Path(root).name
    stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S UTC+8')
    m['Message-ID']='<'+hashlib.sha256((str(Path(root).resolve())+notice['kind']).encode()).hexdigest()+'@qq.com>'
    m.set_content('\n'.join([labels[notice['kind']], '实验：'+Path(root).name,'时间：'+stamp,
        '完成：'+str(notice['finished'])+'/'+str(notice['expected']),
        '评分：'+str(notice['scored'])+'/'+str(notice['expected']),
        '均分：'+str(notice.get('mean_score','尚无汇总')),'原因：'+public_code(notice['reason']),
        '此通知由普通脚本生成，不调用任何模型 API。']))
    return m

def connect(sender,secret):
    smtp=smtplib.SMTP_SSL('smtp.qq.com',465,timeout=20,context=ssl.create_default_context())
    try:smtp.login(sender,secret)
    except BaseException:smtp.close();raise
    return smtp

def deliver(root,notice,sender,secret):
    state=Path(root)/'notification-state.json';previous=read(state)
    if notice['kind'] in previous.get('accepted_events',[]):return True
    if notice['kind'] in previous.get('uncertain_events',[]):return False
    smtp=connect(sender,secret)
    try:
        # A dropped connection during DATA is ambiguous: never pretend delivered
        # and never automatically resend an uncertain mail (duplicate risk).
        refused=smtp.send_message(message(root,notice,sender))
        if refused:raise smtplib.SMTPRecipientsRefused(refused)
    except (OSError,smtplib.SMTPServerDisconnected):
        previous.setdefault('uncertain_events',[]).append(notice['kind'])
        previous.update(state='delivery_uncertain',updated=time.time(),recipient=RECIPIENT)
        save(state,previous);return False
    finally:smtp.close()
    previous.setdefault('accepted_events',[]).append(notice['kind'])
    previous.update(state='smtp_accepted_not_inbox_confirmed',updated=time.time(),recipient=RECIPIENT)
    save(state,previous);return True

def watch(root,sender,secret):
    root=Path(root);state=root/'notification-health.json'
    try:
        smtp=connect(sender,secret);smtp.close()
    except Exception as error:
        save(state,{'state':'configuration_failed','error_type':type(error).__name__,'updated':time.time()});return
    save(state,{'state':'watching','pid':os.getpid(),'recipient':RECIPIENT,'updated':time.time(),'model_calls':0})
    failures=0
    while True:
        try:
            notice=event(root)
            if notice:
                ok=deliver(root,notice,sender,secret)
                save(state,{'state':'smtp_accepted_not_inbox_confirmed' if ok else 'delivery_uncertain',
                    'event':notice['kind'],'recipient':RECIPIENT,'updated':time.time(),'model_calls':0})
                if notice['kind'] in ('completed','terminated') or not ok:return
            failures=0
        except Exception as error:
            failures+=1
            save(state,{'state':'retrying' if failures<5 else 'notification_failed',
                'error_type':type(error).__name__,'updated':time.time(),'model_calls':0})
            if failures>=5:return
        time.sleep(30 if not failures else min(300,30*2**failures))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--detach',action='store_true');args=ap.parse_args();root=args.root.resolve()
    policy=read(Path(__file__).resolve().parent/'notification-policy.json')
    if policy.get('enabled') is False or (root/'notifications-disabled.json').exists():
        print(json.dumps({'state':'disabled_by_user','model_calls':0}));return
    assert (root/'protocol.json').is_file() and (root/'ready.json').is_file()
    credentials=json.loads(sys.stdin.readline());sender=credentials['sender'];secret=credentials['authorization_code']
    assert re.fullmatch(r'[A-Za-z0-9_.+-]+@(qq.com|foxmail.com)',sender) and secret and not any(x.isspace() for x in secret)
    if args.detach:
        import fcntl
        with (root/'notification-start.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            prior=read(root/'notification-launch.json')
            if alive(prior.get('pid')):print(json.dumps({'state':'already_watching'}));return
            smtp=connect(sender,secret);smtp.close() # Authenticate before claiming enabled.
            with (root/'notification-worker.log').open('ab') as out:
                child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--root',str(root)],
                    stdin=subprocess.PIPE,stdout=out,stderr=out,start_new_session=True,text=True)
                child.stdin.write(json.dumps(credentials)+'\n');child.stdin.close()
            save(root/'notification-launch.json',{'pid':child.pid,'recipient':RECIPIENT,'time':time.time(),
                'credential':'fresh encrypted stdin, RAM only','model_calls':0})
        print(json.dumps({'state':'watching_started','recipient':RECIPIENT,'model_calls':0}));return
    watch(root,sender,secret)

if __name__=='__main__':
    try:main()
    except Exception as error:
        # SMTP error bodies can contain identities or auth responses: never print.
        print(json.dumps({'state':'notification_setup_failed','error_type':type(error).__name__}));sys.exit(1)
