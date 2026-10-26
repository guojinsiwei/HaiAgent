// Assertions are checked against retained evidence, never an LLM's paraphrase.
import {checkBasis} from './review-policy.mjs';
export function verificationReceipt(check,row,observed,result=null,context={}) {
  const full=row??observed,execution=result?.isError?'tool_error':full.executed===false?'not_executed':
    !Number.isInteger(full.exitCode)?'unknown':full.exitCode===0?'succeeded':'failed';
  const complete=full.complete===true;
  const assertions=(check.stdout_contains??[]).map(text=>({text,status:typeof full.stdout==='string'&&full.stdout.includes(text)?'met':complete?'not_met':'unknown'}));
  const exact=row?.command===check.arguments.command;
  const diagnostics=[];
  if(!exact)diagnostics.push('No matching evidence for the exact executed command.');
  if(!complete)diagnostics.push('Original observation incomplete; absence cannot be inferred from an excerpt.');
  if(full.shellStageCoverage==='unknown_composite_statuses')diagnostics.push('Top-level exit is known, but composite shell stage exits are not verified.');
  if(row&&row.clean!==true)diagnostics.push('Receipt is not a clean verified command result; this is not automatically an implementation failure.');
  if(assertions.some(a=>a.status!=='met'))diagnostics.push('One or more declared output assertions are unmet or unknown.');
  const valid=!result?.isError&&full.executed===true&&full.exitCode===0&&complete&&exact&&row?.clean===true&&assertions.every(a=>a.status==='met');
  return {command:check.arguments,evidence_id:row?.id??null,command_execution:execution,exitCode:full.exitCode??null,
    observation_complete:complete,assertions,evidence_validity:valid?'valid_check_receipt':'weak_or_partial_evidence',
    harness_diagnostic:diagnostics,requirement_coverage:'must be assessed against original public task; a passing check is not whole-task success',
    execution_identity:{source:'harness',exact_command:exact,call_id:row?.callId??null,model_hash_proof_required:false},
    passed:valid,stdout:full.stdout??'',stderr:full.stderr??'',external_state_verified:false,
    gap_ids:check.gap_ids??[],requirement_quotes:check.requirement_quotes??[],basis:checkBasis(check,context)};
}
