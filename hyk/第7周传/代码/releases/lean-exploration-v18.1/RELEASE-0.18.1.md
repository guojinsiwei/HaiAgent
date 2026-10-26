# BestFGS 0.18.1

This reliability-only revision preserves the v18 continuous action/advisor/
checkpoint/memory policy.  It fixes an overly strict wire setting observed in
the first Long-Horizon TerminalBench run: one malformed JSON response counted
as a complete failed decision, and three adjacent malformed responses could
terminate otherwise productive work.

Each logical model decision may now use at most two API requests.  The second
request is only the existing bounded transport/JSON repair.  Logical
interaction rounds, API request counts, token usage and failure counters remain
separately auditable; no command from an invalid response is executed and task,
tool, wall-clock and advisor budgets are not reset.

The companion LHTB experiment infrastructure separately treats an interim
verifier missing-reward exception as a binary rejection within the same trial,
and distinguishes method failures from infrastructure failures when deciding
whether to admit later tasks.  Those harness changes are not part of the
BestFGS policy package and are sealed in that experiment's protocol hash.
