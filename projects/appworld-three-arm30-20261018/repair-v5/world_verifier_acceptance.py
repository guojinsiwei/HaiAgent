"""Real DSH + Recuris worker + AppWorld, scripted model, isolated network."""
import secrets,json
from pathlib import Path
import runner
runner.V=Path(__file__).resolve().parent
from runner import R,V,read,save,docker,world_args,wait_world,solver_args

def main():
    row=next(x for x in read(R/'protocol.json')['tasks'] if x['task']=='0d01c76_2')
    tag=secrets.token_hex(5);d=V/'acceptance'/('verifier-'+tag)
    for part in ['world','workspace','home','audit']:(d/part).mkdir(parents=True)
    net='aw-v5-check-net-'+tag;world='aw-v5-check-world-'+tag;solver='aw-v5-check-solver-'+tag
    image=read(R/'image.json')['image']
    try:
        docker('network','create','--internal','--label','experiment='+R.name,net)
        docker(*world_args(row,d,net,world,image));ready=wait_world(world);assert not ready['ground_truth_loaded']
        args=solver_args(d,net,solver,'recuris',image);args[0]='run';args.remove('-i');args=args[:-3]
        args+=['-e','KZ_APPWORLD=1','-e','BASELINE_PYTHON=/opt/recuris/bin/python','-e','BASELINE_TEST_ROOT=/tmp/recuris-checks',image,
               '/opt/node/bin/node','--test','/opt/dsh-baselines/tests/appworld-repair.test.mjs']
        p=docker(*args,check=False,timeout=180);(d/'tests.log').write_text(p.stdout+p.stderr)
        print(p.stdout[-5000:]);print(p.stderr[-1000:]);assert p.returncode==0,'AppWorld verification integration failed'
        save(V/'world-verifier-acceptance.json',{'passed':True,'tests':2,'paid_calls':0,'network':'internal','artifacts':str(d),'checks':['genuine public API verification commits receipt','verification write blocked without state mutation','read-only mode restored']})
    finally:
        for name in [solver,world]:docker('rm','-f',name,check=False)
        docker('network','rm',net,check=False)

if __name__=='__main__':main()
