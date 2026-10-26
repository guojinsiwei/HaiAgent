from pathlib import Path

V=Path(__file__).resolve().parent
base=(V.parent/'runner_repair.py').read_text(encoding='utf-8')
base=base.replace('from spending import Ledger,server_for',"sys.path.insert(0,str(Path(__file__).resolve().parent.parent))\nfrom spending import Ledger,server_for")
base=base.replace('R=Path(__file__).resolve().parent', 'V=Path(__file__).resolve().parent\nR=V.parent')
base=base.replace("R/'runtime'/arm", "V/'runtime'/arm")
for name in ['world_server.py','client.py','container-run.mjs']:
    base=base.replace("R/'"+name+"'", "V/'"+name+"'")
base=base.replace("'-v',str(V/'world_server.py')+':/world_server.py:ro'", "'-v',str(V/'appworld_guard.py')+':/appworld_guard.py:ro','-v',str(V/'world_server.py')+':/world_server.py:ro'")
base=base.replace("R/'repair-v1/", "V/'")
base=base.replace("R/'health.json'", "V/'health.json'").replace("R/'summary.json'", "V/'summary.json'").replace("R/'supervisor.log'", "V/'supervisor.log'")
base=base.replace("repair_version=1", "repair_version=2").replace("'version':1,'attempt'", "'version':2,'attempt'").replace("'repair_version':1", "'repair_version':2")
base=base.replace("'Use the documented supervisor task_completed API to submit, including an answer if requested. '", "'Use the documented supervisor complete_task API to submit exactly once, after public read-back. Information requests require an answer; operation-only tasks omit answer. Submission seals application mutations. '")
base=base.replace("'Verify outcomes using ordinary public APIs. Hidden grading feedback is unavailable. No external internet access is required.\\n')", "'Verify outcomes using ordinary public APIs. Hidden grading feedback is unavailable. No external internet access is required.\\n'+POLICY)")
policy='''
PUBLIC APPWORLD EXECUTION RULES
Use collect_pages(apis.APP.API, ...) to explicitly exhaust list APIs; it checks for an empty page and refuses incomplete/repeated pagination. Inspect public API parameters first. The helper defaults to page_limit=5. Do not pass a default first page off as ALL records.
Before a bulk mutation, enumerate the complete candidate set, then select by every public constraint: identity/relationship, time window and semantic description. Yesterday evening is narrower than yesterday; inspect the timestamps and descriptions. Save the original selected records before deletion, retaining all fields to preserve.
Keep writes within the public task. Verify by reading actual results; never send probe messages/payments or export/email artifacts to prove an API path. Deleting a probe may leave global records.
For payment tasks prefer a valid payment card directly. Do not top up a balance or create cross-app payments as a verification step. Any prerequisite writes must be necessary for the public task.
Prepare API assertion scripts in the workspace and execute them inside AppWorld using: python /opt/experiment/client.py --read-only --file /app/check.py
The --file interface executes the script inside the persistent AppWorld interpreter where apis and collect_pages exist. Ordinary local Python does not have apis. Assertions produce a nonzero exit on failure.
Use client.py --read-only for observation and verification. After complete_task, application writes are blocked; continue only read-only verification if needed. Do not create documentation/probe subgoals after completing the requested operation.
'''
base=base.replace("GUIDE='''",'POLICY='+repr(policy)+"\nGUIDE='''",1)
base=base.replace("(d/'workspace/API_GUIDE.md').write_text(GUIDE)","(d/'workspace/API_GUIDE.md').write_text(GUIDE+POLICY)")
(V/'runner.py').write_text(base,encoding='utf-8')
entry=(V.parent/'container-run.mjs').read_text(encoding='utf-8').replace("Object.assign(env,{TAOTOKEN_API_KEY:","Object.assign(env,{KZ_APPWORLD:'1',TAOTOKEN_API_KEY:")
(V/'container-run.mjs').write_text(entry,encoding='utf-8')
print('Built isolated v2 runner; old runner and summaries retained.')
