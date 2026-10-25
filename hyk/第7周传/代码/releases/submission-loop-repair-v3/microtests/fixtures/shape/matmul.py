import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text())
a, b = data['left'], data['right']
if len(a[0]) != len(b):
    raise ValueError(f'dimension mismatch: left columns={len(a[0])}, right rows={len(b)}')
result = [[sum(x*y for x,y in zip(row,col)) for col in zip(*b)] for row in a]
assert result == [[22,28],[49,64]], 'matrix result is incorrect'
print('MATRIX_RESULT=' + json.dumps(result, separators=(',',':')))
