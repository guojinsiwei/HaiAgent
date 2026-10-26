"""Offline regression entry point; never launches experiments or provider calls."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--quick',action='store_true')
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    cases=[('hai',root/'hai', ['test_*.py']),
           ('bestfgs',root/'bestfgs',
            ['test_architecture.py','test_collaboration.py','test_context_updates.py','test_v17_reliability.py']
            if args.quick else ['test_*.py']),
           ('adapter',root/'lhtb-adapter',['test_v17_delivery.py'])]
    failed=[]
    for name,project,patterns in cases:
        env=dict(os.environ, PYTHONUTF8='1')
        env['PYTHONPATH']=os.pathsep.join(map(str,[root/'bestfgs/src',root/'hai/src',root/'bestfgs',
                                                 root/'bestfgs/tests',root/'lhtb-adapter']))
        tests=project if name=='adapter' else project/'tests'
        code=("import unittest,logging; logging.getLogger().addHandler(logging.NullHandler()); "
              "s=unittest.TestSuite(unittest.defaultTestLoader.discover("+repr(str(tests))+",pattern=p) for p in "+repr(patterns)+"); "
              "r=unittest.TextTestRunner(verbosity=1).run(s); raise SystemExit(not r.wasSuccessful())")
        log=root/(name+'-verification.log')
        with log.open('w',encoding='utf-8') as stream:
            completed=subprocess.run([sys.executable,'-c',code],cwd=project,env=env,stdout=stream,stderr=subprocess.STDOUT)
        print(name, 'PASS' if completed.returncode==0 else 'FAIL', str(log),flush=True)
        if completed.returncode:
            failed.append(name)
    return bool(failed)


if __name__=='__main__':
    raise SystemExit(main())
