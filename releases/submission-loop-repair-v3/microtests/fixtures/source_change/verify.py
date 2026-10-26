from pathlib import Path
import sys

namespace = {}
exec(compile(Path(sys.argv[1]).read_text(), sys.argv[1], 'exec'), namespace)
assert namespace['is_valid'](42), 'old rule rejects correct input'
assert not namespace['is_valid'](0), 'new rule must not accept invalid input'
print('SOURCE_CHECK=PASS')
