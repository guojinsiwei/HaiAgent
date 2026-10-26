"""Only zero-API fixture artifacts, never claims or real grades."""
import argparse
import json
from pathlib import Path
from common import ROOT,save,sha,import_tree
from spider_grader import validate_inputs,metadata,official_matcher


def main(task,archive,digest):
    validate_inputs()
    assert task in ('asset001','asana001')
    assert sha(archive)==digest
    output=ROOT/'fixture-roundtrip'/task
    import_tree(archive,output)
    protocol=json.loads((ROOT/'protocol.json').read_text())
    row=next(r for r in protocol['tasks'] if r['task']==task)
    database=output/row['result_path']
    gold,params=metadata(task)
    score=official_matcher()(str(database),str(gold),**params)
    assert score==0,'Unmodified native fixture must remain zero, not a solved trial'
    result=dict(task=task,artifact_sha256=digest,database_sha256=sha(database),
                score=score,roundtrip_verified=True,model_calls=0,not_a_solution=True)
    save(ROOT/'fixture-roundtrip'/(task+'.json'),result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--task',required=True)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--sha256',required=True)
    a=p.parse_args();main(a.task,a.archive,a.sha256)
