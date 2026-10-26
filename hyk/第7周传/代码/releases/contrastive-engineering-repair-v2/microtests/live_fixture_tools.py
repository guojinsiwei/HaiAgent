"""Tiny safe CLI for live model fixtures, not a general shell or benchmark."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

FILES = dict(path=['read_value.py','valid.txt','missing.txt'],
    dependency=['run.py','available/trap_dep.py','trap_dep.py'],
    shape=['matmul.py','case.json','fixed.json'])
WRITABLE = dict(path={'missing.txt'},dependency=set(),shape={'case.json'})
COPIES = dict(path={('valid.txt','missing.txt')},
    dependency={('available/trap_dep.py','trap_dep.py')},shape={('fixed.json','case.json')})
CHECKS = dict(path=['read_value.py','missing.txt'],dependency=['run.py'],shape=['matmul.py','case.json'])
FILES['parameter'] = ['spec.json', 'report.json', 'validate_parameter.py']
WRITABLE['parameter'] = set()
COPIES['parameter'] = set()
CHECKS['parameter'] = ['validate_parameter.py']


def safe_path(root,name,case):
    if name not in FILES[case]: raise ValueError('Path not in fixture allowlist')
    path = root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('Symlinks and outside paths are not allowed')
    return path


def dispatch(root,case,args):
    root = Path(root).resolve()
    if case not in FILES or not args: raise ValueError('Missing fixture or operation')
    op,words = args[0],args[1:]
    if case == 'parameter' and op == 'evaluate' and len(words) == 2 and words[0] == '--threshold':
        threshold = float(words[1])
        if not 0 < threshold <= 1:
            print('ValidationError: threshold must satisfy 0 < threshold <= 1', file=sys.stderr)
            return 2
        safe_path(root, 'report.json', case).write_text(json.dumps(dict(threshold=threshold, loss=threshold/2)), encoding='utf-8')
        print('EVALUATION_PASSED: threshold='+str(threshold)+' loss='+str(threshold/2))
        return 0
    if op == 'list' and not words:
        print(json.dumps([name for name in FILES[case] if safe_path(root,name,case).exists()])); return 0
    if op == 'read' and len(words)==1:
        print(safe_path(root,words[0],case).read_text(encoding='utf-8')[:6000]); return 0
    if op == 'copy' and len(words)==2 and tuple(words) in COPIES[case]:
        shutil.copyfile(safe_path(root,words[0],case),safe_path(root,words[1],case))
        print('COPIED',words[0],'TO',words[1]); return 0
    if op == 'write' and len(words)==2 and words[0] in WRITABLE[case] and len(words[1])<=6000:
        safe_path(root,words[0],case).write_text(words[1],encoding='utf-8')
        print('WROTE',words[0]); return 0
    if op == 'check' and not words:
        # Only trusted, immutable checker code; no model-generated Python is run.
        if case == 'dependency':
            module = safe_path(root,'trap_dep.py',case)
            known = safe_path(root,'available/trap_dep.py',case)
            if module.exists() and module.read_bytes()!=known.read_bytes():
                raise ValueError('Fixture dependency must be the supplied immutable module')
        env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        check = subprocess.run([sys.executable,*CHECKS[case]],cwd=root,env=env,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=8)
        sys.stdout.buffer.write(check.stdout); sys.stdout.buffer.flush()
        sys.stderr.buffer.write(check.stderr); sys.stderr.buffer.flush()
        return check.returncode
    raise ValueError('Allowed CLI: microtool list/read/copy/write/check; only declared fixture paths')


if __name__=='__main__':
    try:
        raise SystemExit(dispatch(sys.argv[1],sys.argv[2],sys.argv[3:]))
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr)
        raise SystemExit(2)
