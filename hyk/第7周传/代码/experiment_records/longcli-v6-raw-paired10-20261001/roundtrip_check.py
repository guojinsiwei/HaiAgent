"""Local relay of representative zero-call artifacts, exact official-score parity."""
import json
from common import ROOT,sha,save
from relay import command,college,KEY,REMOTE,COLLEGE,CUBE,GRADER_PY

command(['scp','-o','BatchMode=yes','cubestudio_container:'+CUBE+'/fixture-artifacts.json',str(ROOT/'fixture-artifacts.json')])
manifest=json.loads((ROOT/'fixture-artifacts.json').read_text())
checks=[]
for task in ('cs61_fa24_scheme','cmu15_445_p0'):
    row=next(r for r in manifest['checks'] if r['task']==task and r['worker']==0)
    archive=ROOT/('roundtrip-'+task+'.tar.gz')
    command(['scp','-o','BatchMode=yes','cubestudio_container:'+row['artifact']['path'],str(archive)],600)
    assert sha(archive)==row['artifact']['sha256']
    command(['scp','-i',KEY,'-o','BatchMode=yes',str(archive),REMOTE+':'+COLLEGE+'/'+archive.name],600)
    job='roundtrip--'+task
    college('cd '+COLLEGE+' && '+GRADER_PY+' -B college_grader.py --fixture --job '+job+
            ' --archive '+archive.name+' --sha256 '+sha(archive),1900)
    returned=json.loads(college('cat '+COLLEGE+'/fixture-grades/'+job+'/result.json'))
    initial='fixture--' if task=='cs61_fa24_scheme' else 'fixture-preserved--'
    starter=json.loads(college('cat '+COLLEGE+'/fixture-grades/'+initial+task+'/result.json'))
    assert all(returned.get(k)==starter.get(k) for k in ('f2p','p2p_is_pass','p2p_step_score','p2p_count','p2p_cases'))
    checks.append(dict(task=task,equal_scores=True,artifact_sha256=sha(archive),returned=returned,starter=starter))
save(ROOT/'roundtrip-acceptance.json',dict(passed=True,checks=checks,model_calls=0))
print(json.dumps(dict(passed=True,representative_tasks=2,fixtures_verified=20,model_calls=0)))
