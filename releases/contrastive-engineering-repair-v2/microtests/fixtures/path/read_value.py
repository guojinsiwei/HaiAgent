from pathlib import Path
import sys

value = int(Path(sys.argv[1]).read_text().strip())
assert value == 42, 'unexpected input value'
print('VALUE=42')
