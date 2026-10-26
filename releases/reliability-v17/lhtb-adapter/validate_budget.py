"""Three resource-bounded, zero-model official budget-delivery fixtures."""
import json
from concurrent.futures import ThreadPoolExecutor
from control import HERE, METHODS, plan, execute
plan()
row = json.loads((HERE / 'manifest.json').read_text())['tasks'][0]
with ThreadPoolExecutor(max_workers=3) as pool:
    for result in pool.map(lambda method: execute(row, method, True), METHODS):
        print(json.dumps(result), flush=True)
