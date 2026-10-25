import json
from pathlib import Path
import sys
from runner import run_one
print(json.dumps(run_one(json.loads(Path(sys.argv[1]).read_text()),fixture=True)))
