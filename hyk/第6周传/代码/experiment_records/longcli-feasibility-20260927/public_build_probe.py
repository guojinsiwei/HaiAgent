"""Build a disposable public-only mirror; original submission stays byte-identical."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parent
source = root / 'inputs/cmu15_445'
scratch = Path(tempfile.mkdtemp(prefix='public-build-', dir=root))
mirror = scratch / 'source'
shutil.copytree(source, mirror, symlinks=True)
cmakelists = mirror / 'CMakeLists.txt'
original = cmakelists.read_bytes()
needle = b'add_subdirectory(test)'
assert original.count(needle) == 1
cmakelists.write_bytes(original.replace(needle, b'if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/test/CMakeLists.txt")\n  add_subdirectory(test)\nendif()'))
cmake = str(root / 'runtime2/bin/cmake')
checks = []
for name, args in [
    ('configure', [cmake, '-S', str(mirror), '-B', str(scratch / 'build'), '-DCMAKE_BUILD_TYPE=Debug']),
    ('primer', [cmake, '--build', str(scratch / 'build'), '--target', 'bustub_primer', '-j2']),
]:
    start = time.time()
    with (root / ('public-' + name + '.log')).open('w') as log:
        p = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            p.wait(timeout=240)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
    checks.append(dict(check=name, exit_code=p.returncode, seconds=time.time()-start))
    print(json.dumps(checks[-1]), flush=True)
    if p.returncode:
        break
assert (source / 'CMakeLists.txt').read_bytes() == original
(root / 'public-build-result.json').write_text(json.dumps({
    'checks': checks, 'scratch': str(scratch), 'original_unchanged': True,
    'original_cmake_sha256': hashlib.sha256(original).hexdigest(),
    'scope': 'public source-only build; not official scoring or a full build',
}, indent=2))
