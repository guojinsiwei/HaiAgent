# Main conversation repair v2

Independent successor to mechanism-integration-fix-v1; neither the frozen
experiments nor the already-validated v1 deployment is overwritten.

## Main conversation

The six-entry evidence/decision dashboard remains a convenience view, not the
main model's entire history. Task-owned conversation records preserve actual
assistant decisions and captured tool feedback. Protocol errors, memory
interventions, restore results, submission rejections and displayed adviser
context are retained with their original roles and historical-state caveats.

`OpenAICompatibleJSONClient` now accepts explicit assistant/user history from the
runner. It has no implicit client-global memory; advisers and separate tasks do
not inherit main-agent dialogue. Wire JSON repair modifies the latest user
message, never an earlier conversation message.

The existing `context_chars=48000` bounds the complete serialized message list,
including system and current task/context, with 1024 characters reserved for a
bounded protocol retry. This is a character budget, not a claim of exact token
measurement. No fixed turn-count eviction is used for conversation.

When full history no longer fits, recent complete pairs remain alongside explicit
older source excerpts and an archive index. These excerpts are deterministic and
partial, not semantic summaries or promises to preserve every fact in the hot
prompt. Full captured records remain in task memory and `conversation_turn` audit
events. `recall_history` searches or reads up to two archived turns per action,
with pagination for long records. Retrieval uses the normal model-round budget
and cannot execute commands. Historical IDs do not bypass current evidence
validation; new memories must cite `fixed_context.evidence`.

Terminal capture limits still apply. Full captured output, rather than just its
short dashboard excerpt, is archived. Secrets are redacted before storage and
before model transmission. No extra summarizer/model calls were added.

## Validation

Local and cloud regressions each passed 233/233 tests. Ubuntu and MATPOWER real
Docker integration runs each passed 15/15 checks; details are in VALIDATION.md.
The cloud suite retains the 13 v1 checks and adds two checks through the actual
JSON transport and real Docker adapter: more than six assistant turns on the
wire, and retrieval of an early observation. Only HTTP response bytes are mocked;
there are no external model API requests or benchmark scoring calls.

The deployment remains opt-in and does not replace existing formal launchers.
`release_tools.py`, `baseline-manifest.json`, `fixed-source-manifest.json` and
`changed-sources.json` provide source provenance. Exact scores or algorithm gains
remain unverified until a separately configured real-model experiment.
