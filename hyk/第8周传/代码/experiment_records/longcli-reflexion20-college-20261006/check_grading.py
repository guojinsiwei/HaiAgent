import json
from common import ROOT, sha

ready = json.loads((ROOT / 'grading-ready.json').read_text())
assert ready['ready'] and sha(ROOT / 'college_grader.py') == ready['grader_sha256'] == ready['historical_grader_sha256']
acceptance = json.loads((ROOT / 'grading-acceptance.json').read_text())
assert acceptance['state'] == 'passed' and acceptance['paid_api_requests'] == 0
assert json.loads((ROOT / 'protocol.json').read_text())['methods'] == ['reflexion']
print(json.dumps({'state': 'grading_accepted', 'paid_api_requests': 0}))
