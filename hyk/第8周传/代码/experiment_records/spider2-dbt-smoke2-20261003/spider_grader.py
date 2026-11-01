"""College-only: run exact official DuckDB comparison functions on frozen artifacts."""
import argparse
import ast
import json
import math
from pathlib import Path
from typing import List, Union

from common import ROOT, save, sha, import_tree


def official_matcher():
    import duckdb
    import pandas as pd
    source=ROOT/'upstream/spider2-dbt/evaluation_suite/eval_utils.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    required=('compare_pandas_table','duckdb_match')
    functions=[next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
               for name in required]
    # The pure local DuckDB scorer does not depend on the unrelated BigQuery import.
    # Compile unmodified official function bodies, not a reimplementation.
    namespace=dict(pd=pd,duckdb=duckdb,math=math,List=List,Union=Union)
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),namespace)
    return namespace['duckdb_match']


def metadata(task):
    path=ROOT/'upstream/spider2-dbt/evaluation_suite/gold/spider2_eval.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    record=next(r for r in rows if r['instance_id']==task)
    assert record['evaluation']['func']=='duckdb_match'
    params=dict(record['evaluation']['parameters'])
    gold=ROOT/'gold'/task/params.pop('gold')
    if not gold.is_file():
        raise RuntimeError('Official gold database unavailable')
    return gold,params


def validate_inputs():
    ready=json.loads((ROOT/'college-ready.json').read_text())
    assert ready['ready']
    for name,expected in ready['hashes'].items():
        if sha(ROOT/name)!=expected:
            raise RuntimeError('Sealed grading input changed: '+name)


def grade(job,archive,expected):
    validate_inputs()
    protocol=json.loads((ROOT/'protocol.json').read_text())
    rows=[r for r in protocol['tasks'] if job=='prediction-off--'+r['task']]
    if len(rows)!=1 or sha(archive)!=expected:
        raise RuntimeError('Unknown job or changed artifact')
    row=rows[0]
    output=ROOT/'grades'/job
    output.mkdir(parents=True,exist_ok=False)
    imported=output/'source'
    import_tree(archive,imported)
    database=imported/row['result_path']
    result=dict(job=job,task=row['task'],artifact_sha256=expected,
                grading_state='failed',official_success=None,score=None)
    try:
        gold,params=metadata(row['task'])
        if not database.is_file():
            result.update(grading_state='complete',official_success=False,score=0,
                          reason='Required output database missing')
        elif database.stat().st_size>256*2**20:
            raise RuntimeError('Output database exceeds the smoke-test bound')
        else:
            import duckdb
            # Reject malformed files distinctly from valid but incorrect tables.
            connection=duckdb.connect(str(database),read_only=True)
            connection.execute('SHOW TABLES').fetchall()
            connection.close()
            score=official_matcher()(str(database),str(gold),**params)
            assert score in (0,1)
            result.update(grading_state='complete',official_success=bool(score),score=int(score),
                          scorer='Unmodified official duckdb_match + compare_pandas_table',
                          gold_sha256=sha(gold))
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error)[:500])
    save(output/'result.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--job',required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    args=parser.parse_args()
    result=grade(args.job,args.archive,args.sha256)
    print(json.dumps(result),flush=True)
    raise SystemExit(0 if result['grading_state']=='complete' else 1)
