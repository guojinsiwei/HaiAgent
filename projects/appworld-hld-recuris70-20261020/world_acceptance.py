"""Check actual client, persistence, isolation, hidden-grader denial and snapshot regrading."""
from runner import R,read,save,docker,world_args,wait_world,grade
from pathlib import Path
import json,os,secrets,urllib.request,urllib.error
def main():
    image=read(R/'image.json')['image'];row=read(R/'task-manifest.json')['tasks'][0]
    probes=[]
    try:
        for i in range(2):
            tag=secrets.token_hex(4);net='aw-check-net-'+tag;name='aw-check-world-'+tag
            d=R/'acceptance'/('world-'+tag);(d/'world').mkdir(parents=True)
            docker('network','create','--internal','--label','experiment='+R.name,net)
            probes.append((net,name,d));docker(*world_args(row,d,net,name,image));wait_world(name)
        def execute(index,code):
            net,_,_=probes[index]
            p=docker('run','--rm','--network',net,'--user',f'{os.getuid()}:{os.getgid()}',
              '-v',str(R/'client.py')+':/client.py:ro',image,'python','-c',
              'import subprocess; p=subprocess.run(["python","/client.py"],input='+repr(code)+',text=True);raise SystemExit(p.returncode)',check=False)
            return p
        assert execute(0,'probe_marker="world-A"; print(probe_marker)').returncode==0
        assert 'world-A' in execute(0,'print(probe_marker)').stdout
        assert 'ABSENT' in execute(1,'print(globals().get("probe_marker","ABSENT"))').stdout
        assert execute(0,'raise ValueError("controlled failure")').returncode==1
        assert 'supervisor' in execute(0,'print(apis.api_docs.show_app_descriptions())').stdout
        net,name,d=probes[0]
        ip=next(iter(json.loads(docker('inspect',name).stdout)[0]['NetworkSettings']['Networks'].values()))['IPAddress']
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:opener.open(urllib.request.Request('http://'+ip+':8080/evaluate',data=b'{}'),timeout=5);raise AssertionError('Grader exposed')
        except urllib.error.HTTPError as e:assert e.code==404
        docker('stop','-t','3',name)
        report=grade(row,d,image);assert report['total_count']>0 and report['success'] is False
        save(R/'world-acceptance.json',{'passed':True,'persistent_cells':True,'separate_worlds':True,'errors_return_nonzero':True,'grader_not_exposed':True,'saved_world_regraded':True,'paid_calls':0})
        print('WORLD_ACCEPTANCE_PASS',flush=True)
    finally:
        for net,name,d in probes:
            logs=docker('logs',name,check=False);(d/'server.log').write_text(logs.stdout+logs.stderr)
            docker('rm','-f',name,check=False);docker('network','rm',net,check=False)
if __name__=='__main__':main()
