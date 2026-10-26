"""Zero-model CPU GUI round-trip and deterministic grader positive/negative control."""
import json
from pathlib import Path
from environments import WebEnvironment
out=Path('/output');out.mkdir(exist_ok=True)
task={'sites':['reddit'],'require_login':False,'start_url':'about:blank','intent':'deployment canary',
      'eval':{'eval_types':['program_html'],'program_html':[{'url':'last','locator':'document.body.dataset.done','required_contents':{'exact_match':'verified'}}]}}
env=WebEnvironment(task,out)
try:
    env.reset();evidence=env.transport_preflight()
    env.page.set_content('<body data-done="pending"></body>')
    negative=env.evaluate();assert negative==0
    env.page.set_content('<body data-done="verified"></body>')
    positive=env.evaluate();assert positive==1
    (out/'browser-preflight.json').write_text(json.dumps({'passed':True,'transport':evidence,'negative_score':negative,'positive_score':positive,'model_calls':0}))
    print('CPU_BROWSER_PREFLIGHT_PASSED',flush=True)
finally:env.close()
