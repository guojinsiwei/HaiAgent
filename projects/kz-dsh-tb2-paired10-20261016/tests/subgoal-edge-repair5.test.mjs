import test from 'node:test';
import assert from 'node:assert/strict';
import {Subgoals,substantiveSilentCheck} from '../src/subgoals.mjs';
import {SubgoalController} from '../src/subgoal-controller.mjs';
import {FullTask} from '../src/full-task.mjs';
import {Policy,actionKey} from '../src/policy.mjs';
import {CriticCache} from '../src/critic-cache.mjs';
import {clip} from '../src/terminal.mjs';

const deps={'a.py':'file:a'},goal={id:'G1',title:'parser',acceptance:'public parser behavior passes',targets:['a.py'],depends_on:[]};
for(const command of ['go test -list=.', 'go test -n', 'go test -c'])test(`R5 edge: Go preview ${command} cannot certify execution`,()=>{
  assert.equal(substantiveSilentCheck({command}),false);
});
for(const command of ['make test -n','make test -q','make test --just-print','make test --recon','make test --question','ctest -N','ctest -NV','ctest --show-only=json-v1','cargo test --no-run','pytest --collect-only','pytest --co','python -m pytest --fixtures','npm test -- --listTests','npm test -- --showConfig','python -m doctest -o SKIP a.py','python -m doctest -oSKIP a.py','python -m doctest --option=SKIP a.py','go test -list .'])test(`R5 edge: list/dry-run ${command} cannot certify a silent test`,()=>{
  assert.equal(substantiveSilentCheck({command}),false);
  const goals=new Subgoals();assert.throws(()=>goals.define({subgoal_plan:[{...goal,verification:{arguments:{command},exit_code:0,stdout_contains:[]}}]}),/substantive/);
});

for(const command of ['python -B -m doctest a.py','python -u -m doctest a.py','python -E -m doctest a.py','python -I -m doctest a.py','python -s -m doctest a.py','python -Bu -m doctest a.py'])test(`R5 edge: supported interpreter flags do not reject a real silent test: ${command}`,()=>{
  assert.equal(substantiveSilentCheck({command}),true);
  const goals=new Subgoals();assert.doesNotThrow(()=>goals.define({subgoal_plan:[{...goal,verification:{arguments:{command},exit_code:0,stdout_contains:[]}}]}));
});

test('R5 edge: initial goal lacking verification is safe through actual CriticCache eligibility and lookup',()=>{
  const task=new FullTask({}),cache=new CriticCache();task.goals.define({subgoal_plan:[goal]});
  const check={arguments:{command:'python -m doctest a.py'},cache_scope:'workspace',stdout_contains:[]};
  assert.equal(cache.eligible(check,task),false);assert.equal(cache.get(check,task),null);
});

test('R5 edge: candidate hints remain bounded in the structured prompt while full arguments stay in evidence',()=>{
  const task=new FullTask({fullContextChars:8000,memoryReserveChars:3000}),policy=new Policy();
  task.goals.define({subgoal_plan:[{...goal,title:'Large public requirement '+ 'x'.repeat(100000)}]});
  const args={command:'python -m pytest test_a.py -k '+ 'x'.repeat(100000),description:'y'.repeat(100000)};
  const row={id:'E1',tool:'bash',executed:true,complete:true,exitCode:0,clean:true,category:'test',command:args.command,arguments:args,key:actionKey({name:'bash',arguments:args}),stdout:'31 passed',stderr:'',dependenciesBefore:deps,dependenciesAfter:deps,before:'sha256:a',after:'sha256:a'};
  task.state.evidence={E1:row};task.state.dependencies=deps;task.state.scope='sha256:a';
  const control=new SubgoalController().tick(task.goals,{evidence:task.state.evidence,dependencies:deps});
  task.state.subgoalControl=control.view;if(control.notice)task.notice(clip(control.notice,2400));
  const panel=task.panel(policy);assert.ok(panel.text.length<=8000,`prompt length ${panel.text.length}`);
  assert.ok(task.state.evidence.E1.arguments.command.length>100000);assert.equal(panel.result.subgoal_controller.verification_candidates[0].arguments,undefined);
  assert.equal(panel.result.subgoal_controller.verification_candidates[0].arguments_ref,'kz_history id=E1');assert.equal(task.goals.state.items.G1.status,'pending');
});

test('R5 edge: missing plan reminders never block an ordinary native action',()=>{
  const task=new FullTask({}),policy=new Policy(),controller=new SubgoalController();
  for(let n=0;n<30;n++) {
    const control=controller.tick(task.goals,{observed:n,requests:n,dependencies:deps});assert.equal(control.view.blocking,false);
    assert.equal(task.before({name:'bash',arguments:{command:'cat a.py'},callId:`c${n}`},policy,'sha256:a',deps).allowed,true);
  }
  assert.equal(controller.state.planPrompts,2);assert.equal(Object.keys(task.goals.state.items).length,0);
});
