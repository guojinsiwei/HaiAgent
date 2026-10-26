import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {requirementCatalog,normalizeCritic,uncoveredCatalog} from '../src/public-contract.mjs';
import {assessProgress,stalledDelivery} from '../src/mechanism-evidence.mjs';
import {TaskMemory} from '../src/memory.mjs';
import {reviewAdmission,completionProgress} from '../src/review-stability.mjs';
import {CompletionLedger} from '../src/completion.mjs';
import {coverageValid} from '../src/review-policy.mjs';
import {progressView,deliveryPaths} from '../src/progress.mjs';

test('monetary pressure enters delivery priority before the cap and compiled artifacts are tracked',()=>{
 const s={taskGoal:'Write output.c and save output.elf.',usage:{requests:1,tools:1},cost:{spentUpperCny:7,pendingUpperCny:0}};
 progressView(s,{maxRequests:400,maxTools:600,costPolicy:{limitCny:8}},{});
 assert.equal(s.budgetView.phase,'delivery_priority');assert.deepEqual(deliveryPaths(s.taskGoal),['output.c','output.elf']);
});

test('real audited task formats retain every substantive line and resolve all Q references',()=>{
 const fixtures=JSON.parse(readFileSync(new URL('../../catalog-fixtures.json',import.meta.url)));
 for(const {task} of fixtures){
  const catalog=requirementCatalog(task);assert.ok(catalog.length);
  for(const line of task.split('\n').filter(x=>x.trim()))assert.ok(catalog.some(q=>q.quote.includes(line.trim())),line);
  assert.deepEqual(requirementCatalog(task),catalog);
  const out=normalizeCritic({requirement_refs:catalog.map(q=>q.id)},catalog);
  assert.deepEqual(out.requirements,catalog.map(q=>q.quote));
 }
});
test('numbered constraints, examples and fenced blocks are lossless; empty input stays unavailable',()=>{
 const task='Build report.csv\n\n## No network access\n1. Keep all rows.\n2. Keep zero values.\n\n```text\na\n\nb\n```';
 const c=requirementCatalog(task);assert.ok(c.some(q=>q.quote==='```text\na\n\nb\n```'));
 assert.ok(c.some(q=>q.quote.includes('No network')));assert.deepEqual(requirementCatalog('  '),[]);
 assert.ok(uncoveredCatalog({requirements:[c[0].quote]},c).length);
});
test('full contract needs attributed receipts for every segment; subset accept cannot pass',()=>{
 const task='Keep every row.\n\nPreserve zero values.',catalog=requirementCatalog(task);
 const receipts=[{evidence_id:'E1',passed:true,requirement_quotes:catalog.map(q=>q.quote),basis:{level:'attributed_correctness_basis'}}];
 const verdict=normalizeCritic({requirement_refs:catalog.map(q=>q.id),requirement_evidence:catalog.map(q=>({requirement_ref:q.id,evidence_ids:['E1'],reason:'Fixture independent expected rows and zero case'}))},catalog);
 assert.deepEqual(uncoveredCatalog(verdict,catalog),[]);assert.equal(coverageValid(verdict,receipts,task),true);
 verdict.requirements.pop();assert.deepEqual(uncoveredCatalog(verdict,catalog),['Q2']);
});
const row=(i,text='count=3')=>({id:'E'+i,key:'check',complete:true,executed:true,stdout:text,stderr:'',exitCode:0,semanticRoute:'D1'});
test('progress needs a new attributable predicate; new E ID with same measurement does not inflate progress',()=>{
 const state={},catalog=requirementCatalog('Keep three rows.');
 const review={verdict:'progress',reason:'tested',evidence_ids:['E1'],progress_claim:{requirement_ref:'Q1',kind:'requirement_check',predicate:'row count',expected_basis:'public task three rows',support:[{evidence_id:'E1',field:'stdout',quote:'count=3'}]}};
 assert.equal(assessProgress(review,state,catalog,{E1:row(1)}).accepted,true);
 const again=structuredClone(review);again.evidence_ids=['E2'];again.progress_claim.support[0].evidence_id='E2';
 assert.equal(assessProgress(again,state,catalog,{E2:row(2)}).review.verdict,'uncertain');
 assert.equal(assessProgress({...review,progress_claim:undefined},{},catalog,{E1:row(1)}).accepted,false);
 assert.equal(assessProgress(review,{},catalog,{E1:{...row(1),nativeToolError:true}}).accepted,false);
});
test('unchanged delivery with twelve executions requests reassessment; changed artifact resets alarm',()=>{
 const s={delivery:{requested_artifacts:['out.c']},dependencies:{'out.c':'file:a'},evidence:{E1:row(1)}};
 assert.deepEqual(stalledDelivery(s,{accepted:false},'D1'),[]);
 for(let i=2;i<=7;i++)s.evidence['E'+i]=row(i);
 assert.deepEqual(stalledDelivery(s,{accepted:false},'D1'),[]);
 for(let i=8;i<=13;i++)s.evidence['E'+i]=row(i);
 assert.equal(stalledDelivery(s,{accepted:false},'D1').length,6);
 s.dependencies['out.c']='file:b';assert.deepEqual(stalledDelivery(s,{accepted:false},'D1'),[]);
});
test('contradicted memory ceases to gate actions; quoted newer observations required and dispute persists',()=>{
 const m=new TaskMemory(),e={E1:{...row(1),after:'sha256:a'},E2:row(2,'count=4')};
 const item=m.admit({kind:'blocker',conclusion:'three rows',condition:'same input',targets:[],evidence_ids:['E1'],commandKey:'x'},e,['E1'],'sha256:a',{});
 assert.throws(()=>m.correct({ids:[item.id],reason:'different',support:[{evidence_id:'E2',field:'stdout',quote:'invented'}]},e));
 m.correct({ids:[item.id],reason:'new count disagrees',support:[{evidence_id:'E2',field:'stdout',quote:'count=4'}]},e);
 assert.equal(m.applicability(item,'sha256:a',{}),'disputed_claim_recheck_required');
 assert.equal(m.recall('rows','sha256:a',{})[0].current,false);
 assert.ok(new TaskMemory(JSON.parse(JSON.stringify(m.state))).state.items[0].disputed);
});
test('repeat review cannot be unlocked by scratch edits or duplicated receipts, while new actual evidence can',()=>{
 const s={scope:'sha256:a',delivery:{requested_artifacts:['out.c']},dependencies:{'out.c':'file:a'},evidence:{E1:row(1)}};
 const l=new CompletionLedger();assert.equal(reviewAdmission(s,null,l).allowed,true);
 const before=completionProgress(s,l);s.scope='sha256:scratch';s.evidence.E2=row(2);
 s.subgoals={items:{G1:{definition:{targets:['scratch-check.py']}}}};s.dependencies['scratch-check.py']='file:new-check';
 assert.equal(completionProgress(s,l),before);assert.equal(reviewAdmission(s,null,l).allowed,false);
 s.evidence.E3=row(3,'count=4');assert.equal(reviewAdmission(s,null,l).allowed,true);
 s.dependencies['out.c']='file:b';assert.notEqual(completionProgress(s,l),before);
});
