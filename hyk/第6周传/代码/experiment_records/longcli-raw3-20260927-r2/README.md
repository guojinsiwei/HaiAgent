# LongCLI Raw3 repair revision 2

The old run is preserved at /mnt/lizh639/longcli-raw3-20260927. Scheme stopped after
29 model responses and 29 tools because the API transport failed twice. It was not
a completed solution or an official failure; Ants/Cats did not start.

Changes are infrastructure-only: actual null/zero/random/urandom device nodes in
the isolated roots; bounded transport recovery; continuation from audited history.
Model, tasks, prompts, method and original total budgets remain the same. The prior
126.50847 s of active time is subtracted from Scheme's 7200 s allowance. Recovery
backoff and replay overhead consume the remaining allowance; offline downtime does not.

Scheme's recorded 29 responses and 29 tool results are replayed WITHOUT network
requests or command execution to reconstruct the normal runtime history. Before
the next real request, the full conversation must match the last failed request,
except remaining budgets and controller-to-sandbox workspace path translation.
Replay events are labelled. Interaction/tool counters include those 29 historical
actions, so do NOT add the old 29 again to the new result counters. API costs are
summed from actual API events across revisions; replay creates no API events.

Transient transport errors, 408/429 and server errors can receive 3 extra retry
cycles per request, at most 6 cycles per task, waiting 10/30/60 s. Each cycle retains
the original 2-attempt client bound. Authentication/payment and format failures are
not silently retried by this recovery layer. Exhaustion still stops the worker.

Validation: real bash redirection and Python null/zero/random device IO in all three
sandboxes; offline exact-context replay with zero real API/tool execution; four
offline tests for transient recovery, auth refusal and per-request/per-task limits.
Source roots and artifacts from revision 1 are not overwritten.

Start using Resume-LongCLIRaw3.ps1 with private key input. The predecessor removed
its temporary key on exit; there is no credential to reuse. A prepared revision is
not a running experiment. Inspect the cloud health.json after launch.
