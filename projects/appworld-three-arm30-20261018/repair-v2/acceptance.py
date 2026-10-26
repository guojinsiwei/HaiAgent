"""Actual isolated AppWorld + official grading, no model/provider access."""
import json,secrets,urllib.request,urllib.error,os
from pathlib import Path
from runner import R,V,read,save,docker,world_args,wait_world,grade

def main():
    manifest=read(R/'protocol.json')['tasks']
    row=next(x for x in manifest if x['task']=='13547f5_2')
    image=read(R/'image.json')['image'];tag=secrets.token_hex(5)
    d=V/'acceptance'/tag;(d/'world').mkdir(parents=True)
    net='aw-v2-check-net-'+tag;name='aw-v2-check-world-'+tag
    try:
        docker('network','create','--internal','--label','experiment='+R.name,net)
        docker(*world_args(row,d,net,name,image));ready=wait_world(name)
        assert not ready['ground_truth_loaded']
        ip=next(iter(json.loads(docker('inspect',name).stdout)[0]['NetworkSettings']['Networks'].values()))['IPAddress']
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def execute(code,ro=False):
            req=urllib.request.Request('http://'+ip+':8080/execute',data=json.dumps({'code':code,'read_only':ro}).encode(),headers={'Content-Type':'application/json'})
            with opener.open(req,timeout=90) as response:return json.load(response)
        code='''
pws=apis.supervisor.show_account_passwords()
pw=next(p['password'] for p in pws if p['account_name']=='phone')
me=apis.supervisor.show_profile()
tok=apis.phone.login(username=me['phone_number'],password=pw)['access_token']
partners=apis.phone.search_contacts(access_token=tok,relationship='partner')
assert len(partners)==1
number=partners[0]['phone_number']
sent=apis.phone.send_text_message(access_token=tok,phone_number=number,message='The dishwasher is clean and ready to be emptied.')
print('REQUESTED_MESSAGE_SENT')
'''
        # Read-only mode is enforced at the actual requester, even if Python
        # catches its own API errors. No messages may appear from this cell.
        blocked=execute(code,True)
        assert 'APPWORLD_READ_ONLY' in blocked['output'],blocked
        assert blocked['guard']['revision']==0
        actual=execute(code)
        assert 'REQUESTED_MESSAGE_SENT' in actual['output'],actual
        answer=execute("apis.supervisor.complete_task(answer='unrequested explanatory text'); print('SUBMITTED')")
        assert answer['guard']['submitted'] and any(x['kind']=='state_only_answer_normalized' for x in answer['guard_events']),answer
        probe=execute("apis.phone.send_text_message(access_token=tok,phone_number=number,message='KZCHECK-DELETEME')")
        assert 'APPWORLD_READ_ONLY' in probe['output'],probe
        verify=execute("rows=collect_pages(apis.phone.search_text_messages,access_token=tok,phone_number=number); assert len(rows)>5; print('PAGINATED',len(rows))",True)
        assert 'PAGINATED' in verify['output'] and not verify['output'].startswith('Execution failed'),verify
        # Check the documented file execution path, including real client exit.
        checker=d/'check.py';checker.write_text("assert len(collect_pages(apis.phone.search_text_messages,access_token=tok,phone_number=number))>5\nprint('FILE_CHECK_OK')\n")
        p=docker('run','--rm','--network',net,'--user',f'{os.getuid()}:{os.getgid()}',
          '-v',str(V/'client.py')+':/client.py:ro','-v',str(checker)+':/check.py:ro',image,'python','/client.py','--read-only','--file','/check.py',check=False)
        assert p.returncode==0 and 'FILE_CHECK_OK' in p.stdout,p.stderr+p.stdout
        try:opener.open(urllib.request.Request('http://'+ip+':8080/evaluate',data=b'{}'),timeout=5);raise AssertionError('grader exposed')
        except urllib.error.HTTPError as ex:assert ex.code==404
        docker('stop','-t','3',name);g=grade(row,d,image)
        assert g['success'] and g['pass_count']==g['total_count'],g
        save(V/'world-acceptance.json',{'passed':True,'task':row['task'],'grade':[g['pass_count'],g['total_count']],
          'checks':['actual requester read-only','post-submit probe blocked','state-only answer contract','pagination exhaustion','direct client --file','hidden grader unavailable','official grade persisted'],
          'paid_calls':0,'artifacts':str(d)})
        print('WORLD_ACCEPTANCE_PASS',g['pass_count'],g['total_count'])
    finally:
        logs=docker('logs',name,check=False);(d/'server.log').write_text(logs.stdout+logs.stderr)
        docker('rm','-f',name,check=False);docker('network','rm',net,check=False)

if __name__=='__main__':main()
