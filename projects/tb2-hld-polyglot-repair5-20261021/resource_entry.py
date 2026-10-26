"""Expose the container's CPU quota through inherited process affinity."""
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def quota_cpus():
    parts = Path('/sys/fs/cgroup/cpu.max').read_text().split()
    return None if parts[0] == 'max' else max(1, math.ceil(int(parts[0]) / int(parts[1])))


def main():
    allowed = sorted(os.sched_getaffinity(0))
    quota = quota_cpus()
    if quota is None:
        raise RuntimeError('Expected the official finite CPU quota')
    count = min(len(allowed), quota)
    seed = os.environ.get('PAIRED_ATTEMPT_ID', str(os.getpid()))
    offset = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % len(allowed)
    selected = [allowed[(offset + i) % len(allowed)] for i in range(count)]
    os.sched_setaffinity(0, selected)
    for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
                'CMAKE_BUILD_PARALLEL_LEVEL', 'MAX_JOBS'):
        os.environ[key] = str(count)
    os.environ.setdefault('MAKEFLAGS', '-j' + str(count))
    out = Path('/logs/agent/resource-awareness.json')
    out.write_text(json.dumps(dict(quota_cpus=quota, affinity=selected,
                                  prior_visible_cpus=len(allowed), memory_limit_unchanged=True)))
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == '__main__':
    main()
