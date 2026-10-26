import test from 'node:test';
import assert from 'node:assert/strict';
import {CompletionLedger} from '../src/completion.mjs';
import {preflightChecks,checkBasis,coverageValid} from '../src/review-policy.mjs';
import {verificationReceipt} from '../src/verification-receipt.mjs';
const task='Compute total using public factor 2. Preserve pending notifications after failure.';
const quote='public factor 2';
const basis={author:'critic',kind:'public_spec',expected_rule:quote,sources:[{kind:'task',quote}],independence:'Expected factor is explicitly supplied by the task, not recovered from candidate code.'};
const check={arguments:{command:'python check.py'},stdout_contains:['passed'],gap_ids:['Gap-1'],requirement_quotes:[quote],provenance:basis};
const row={id:'E2',key:'check',command:check.arguments.command,executed:true,complete:true,clean:true,exitCode:0,stdout:'passed',stderr:''};
const receipt=c=>verificationReceipt(c,row,{},null,{publicTask:task});
const ctx={scope:'sha256:a',dependencies:{'code.py':'file:a'},evidence:{E2:row},observed:2,publicTask:task};
const close={gap_id:'Gap-1',status:'closed',evidence_ids:['E2'],reason:'The new test asserts the public factor independently of the candidate implementation.'};
function ledger() {const l=new CompletionLedger();l.registerReview({new_gaps:[{requirement_quote:quote,detail:'Formula premise unverified',proof_obligation:'correctness_basis'}]},task);return l;}

test('EC3 historical fin failure: global accept plus column-only receipt cannot close formula gap',()=>{
  const l=ledger();l.record({decision:'accept',requirements:[quote],gaps:[]},[{evidence_id:'E2',passed:true}],{...ctx,accepted:true});
  assert.equal(l.open().length,1);assert.equal(l.state.status,'repair_pending');
});
test('EC3 explicit targeted closure succeeds; unrelated second gap stays open',()=>{
  const l=ledger();l.upsert('notifications',{detail:'Notification not observed'});
  l.record({gap_updates:[close]},[receipt(check)],{...ctx,accepted:true});
  assert.deepEqual(l.open().map(g=>g.id),['Gap-2']);assert.equal(l.state.status,'repair_pending');
});
for(const variant of ['no_mapping','wrong_requirement','no_reason','unknown_id','consistency','cached'])test(`EC3 formula closure rejects ${variant}`,()=>{
  const l=ledger(),c=structuredClone(check),update={...close};let r;
  if(variant==='no_mapping')c.gap_ids=[];
  if(variant==='wrong_requirement')c.requirement_quotes=['Preserve pending notifications after failure.'];
  if(variant==='no_reason')delete update.reason;
  if(variant==='unknown_id')update.evidence_ids=['E999'];
  if(variant==='consistency')c.provenance.kind='self_consistency';
  r=receipt(c);if(variant==='cached')r.reused_current_receipt=true;
  l.record({gap_updates:[update]},[r],{...ctx,accepted:true});assert.equal(l.open().length,1);
});
test('EC3 plan-stage gaps survive a verdict that omits them and checkpoint restore',()=>{
  let l=ledger();l=new CompletionLedger(JSON.parse(JSON.stringify(l.state)));
  l.record({gaps:[],decision:'accept'},[],{...ctx,accepted:true});assert.equal(l.open()[0].detail,'Formula premise unverified');
});
test('EC3 a repeated or weaker plan cannot downgrade an existing correctness obligation',()=>{
  const l=ledger();l.registerReview({new_gaps:[{requirement_quote:quote,proof_obligation:'behavior',detail:'Formula premise unverified'}]},task);
  assert.equal(l.open()[0].proof_obligation,'correctness_basis');
});
test('EC3 distinct deficiencies under the same public requirement are not merged',()=>{
  const l=ledger();l.registerReview({new_gaps:[{requirement_quote:quote,detail:'Input boundary missing',proof_obligation:'behavior'}]},task);
  assert.equal(l.open().length,2);
  l.record({gap_updates:[close]},[receipt(check)],{...ctx,accepted:true});assert.deepEqual(l.open().map(g=>g.detail),['Input boundary missing']);
});
test('EC3 exact public source traced; fabricated or incomplete evidence remains consistency-only',()=>{
  assert.equal(checkBasis(check,{publicTask:task}).level,'attributed_correctness_basis');
  const c={...check,provenance:{...basis,sources:[{kind:'evidence',evidence_id:'E1',field:'stdout',quote}]}};
  assert.equal(checkBasis(c,{evidence:{E1:{stdout:quote,complete:false}}}).level,'consistency_only');
  assert.equal(checkBasis(c,{evidence:{E1:{stdout:'not the expected rule',complete:true}}}).level,'consistency_only');
});
test('EC3 task correctness coverage requires mappings for each requirement',()=>{
  const verdict={requirements:[quote],requirement_evidence:[{requirement_quote:quote,evidence_ids:['E2'],reason:'The test exercises the supplied factor.'}]};
  assert.equal(coverageValid(verdict,[receipt(check)],task),true);
  assert.equal(coverageValid({...verdict,requirements:[quote,'Preserve pending notifications after failure.']},[receipt(check)],task),false);
  assert.equal(coverageValid(verdict,[receipt({...check,provenance:{...basis,kind:'self_consistency'}})],task),false);
});
test('EC3 missing information or capability is a legal zero-execution, zero-verdict-call plan',()=>{
  for(const kind of ['missing_information','missing_capability','repair_check','repair_implementation']) {
    const p={decision:'revise',reason_kind:kind,gaps:['Expected rule has no supplied source'],checks:[],next_step:'Read the public rule before choosing an expected value.'};
    assert.equal(preflightChecks(p,{publicTask:task}).needsInformation,true);
  }
  assert.equal(preflightChecks({decision:'accept',checks:[]},{publicTask:task}).ok,false);
});
test('EC3 payments-like composite plans are rejected before any execution; direct scripts remain valid',()=>{
  for(const command of ["python - <<'PY'\nprint('passed')\nPY",'python check.py; echo passed','python check.py | tail -1','bash -c "python check.py"'])
    assert.equal(preflightChecks({checks:[{...check,arguments:{command}}]},{publicTask:task}).ok,false,command);
  for(const command of ['python check.py',"python -c 'assert 2 + 2 == 4; print(4)'"])
    assert.equal(preflightChecks({checks:[{...check,arguments:{command}}]},{publicTask:task}).ok,true,command);
});
test('EC3 a new contradictory result still invalidates individually mapped proof',()=>{
  const l=ledger();l.record({gap_updates:[close]},[receipt(check)],{...ctx,accepted:true});assert.equal(l.open().length,0);
  l.sync('sha256:a',ctx.dependencies,{E3:{...row,id:'E3',exitCode:1}},3);assert.equal(l.open().length,1);
});
