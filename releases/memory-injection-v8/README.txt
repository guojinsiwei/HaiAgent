BestFGS memory injection v8 (local candidate, not deployed)

Base: exact LHTB five-arm experiment common source, incorporating v7 and v6.1 fixes.
Existing releases, experiment arms and results are NOT modified.

The former 2500-character reserve belongs to prompt_views/context_and_memory,
used by the structured collaboration adapter. LHTB's LeanTaskRunner used a
different panel, where memories could be popped during input compaction.

Changes:
- Reserved whole memory views, default 8000 characters INSIDE the original
  48000-character request budget. Full provenance stays in the memory store/audit.
- Remove delivery-progress duplication of the complete task; preserve task.goal.
- Compact observations before touching protected memory; report reserve omissions.
- Move fixed_context to the last field, memories and decision contract to its tail.
- Trusted system instruction requires brief memory_review before executing an
  action with visible memories. Failed unchanged attempts should change route or
  specify a discriminating observation. Stale claims remain untrusted evidence.
- Reflection-first update: when memories are visible, the response must begin
  with memory_review, strategy_adjustment, action IN THIS ORDER. memory_review
  gives the observed historical result and current applicability; adjustment
  specifies the concrete change/recheck and its verification. Missing/reordered
  fields are refused before execution. The action remains a top-level string.
- Two demonstrations show changing an unchanged failed attempt, and repeating
  the SAME verification after source changes. They are explicitly illustrative,
  not task evidence. No similarity threshold or novelty-for-novelty requirement.
- Historical assistant messages retain the same reflection-first field order;
  canonical audit archives remain unchanged. Only brief decision summaries are
  requested, not private or extended reasoning.
- No extra LLM call, no increase to tool/model/output budgets. This schema checks
  the presence of a decision summary, NOT the truth or effectiveness of its claim.
  A claim of changing route cannot repeat the exact command already linked to an
  applicable blocker; such a retry must explicitly specify justified_retry and
  new_evidence. This is not a general semantic-loop detector.
- Command-identity repair: for one static simple `bash/sh -c/-lc` command,
  normalize separator spaces/tabs and literal argument quoting with a guarded
  shlex pass. The shared key feeds automatic observations, memory matching and
  execution gating. Execution receives the original argv, not a rewritten command.
  Quoted data whitespace, argument order/values, cwd, stdin and shell flags stay
  significant. Preserve command-word spelling because quoting can affect aliases.
  Expansions, globs, pipelines, redirection, comments, compound programs and
  malformed syntax retain raw identity; this is deliberately NOT a shell parser.
- final_prompt events contain the full logical message list. wire_prompt events
  contain actual API request bodies, including format-repair retries. Credentials
  and known secrets are redacted; headers/endpoints are not logged.
- terminal_text.py makes readable terminal projections: removes CSI/OSC/DCS
  styling/cursor/title controls, preserves CR refresh frames as separate lines,
  and marks incomplete sequences. Does NOT emulate erasure/cursor rewriting.
  Captured originals remain in tool_call.result (subject to executor capture
  limits); model/history views are cleaned. Assessments use readable output;
  uncertain projections cannot create automatic lessons or prove check success.
- advisor_handover.py builds a bounded report before every consultation, including
  goal reference, latest historical problem, up to three observed failure groups,
  relevant memories and evidence IDs. Writes latest-handover.json even if adviser
  capacity is unavailable. No invented strategies, causal inference or extra LLM
  call. The actual adviser request receives the report inside its existing budget.

Core: sources/bestfgs-project/src/bestfgs/memory_injection.py and lean_runtime.py.
Switch: LeanConfig(memory_injection=False) restores old injection behavior.
Old reliability tests explicitly disable the new contract to test legacy behavior;
test_memory_injection.py tests the enabled behavior and refusal of missing reviews.

replay_context.py replays the completed C1 Foldseek request states without API,
Docker or commands. It tests delivery of memory, not improvement in task reward.
No paid experiment, production deployment, or desktop-package replacement is performed.
Isolated real-command validation on the college server is recorded separately in
evidence/microtests (before repair) and evidence/microtests-normalized (after repair).
The later ANSI/handover build is verified by 118 Linux regression tests and the
original twelve engineering runs in evidence/microtests-handover-ansi.
Start-LiveMemory.ps1 prepares six REAL provider continuations after controlled
failures; it requires the user's hidden local key input. See LIVE_TEST_PROTOCOL.txt.
The first live run has now completed: all six toy goals passed, 35 API calls.
Memory reviews were present, but controls also solved all three cases; no memory
advantage demonstrated. Results: evidence/live-memory-reviewed-bMpgaM/RESULTS.txt.
Do not restart the existing output directory or confuse the microtest with a benchmark.

Inspect a saved request:
python inspect_prompt.py <run>/events.jsonl --role action --request 100
Add --attempt 2 to inspect the actual second wire attempt, including repair text.
python verify_sources.py verifies candidate and unchanged frozen-source hashes.
