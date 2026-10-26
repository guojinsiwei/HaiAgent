"""Validate all selected environments and official success on separate training tasks."""
from pathlib import Path
import collections,json,tempfile,time
from world_server import World
from alfworld.agents.expert import HandCodedTWAgent

R=Path('/experiment')
manifest=json.loads((R/'manifest.json').read_text())
rows=manifest['selected'];assert len(rows)==80 and len({r['id'] for r in rows})==80
results=[]
for row in rows:
    with tempfile.TemporaryDirectory() as tmp:
        w=World(Path('/data')/row['game'],tmp)
        assert not w.view()['won'] and w.view()['observation']
        assert w.view()['actions']
        before=w.steps
        first=w.step('look','idempotence');second=w.step('look','idempotence')
        assert first==second and w.steps==before+1
        try:w.step('inventory','idempotence')
        except ValueError:pass
        else:raise AssertionError('Duplicate-id mutation not rejected')
        w.env.close()
    results.append(dict(id=row['id'],reset=True,idempotence=True))
    print('RESET_OK',row['id'],flush=True)
training=[]
for row in manifest['preflight_training']:
    with tempfile.TemporaryDirectory() as tmp:
        game=Path('/data')/row['game'];w=World(game,tmp,max_steps=150,training_probe=True)
        expert=HandCodedTWAgent(max_steps=150);expert.reset(str(game));previous='look'
        # The built-in expert is only used here on training tasks, never in paid worlds.
        expert.observe(w.state.feedback)
        for index in range(150):
            action=expert.act(w.state,0,bool(w.state.won),previous)
            w.step(action,str(index));previous=action
            if w.done:break
        assert w.view()['won'],f'Training success probe failed: {row["id"]}'
        before=w.steps;w.step('look','after-win');assert w.steps==before
        assert json.loads((Path(tmp)/'state.json').read_text())['won']
        training.append(dict(type=row['type'],steps=w.steps,official_won=True));w.env.close()
out=dict(passed=True,selected_resets=len(results),training_successes=training,paid_calls=0,
         model_calls=0,results=results,completed=time.time())
(R/'preflight-result.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out),flush=True)
