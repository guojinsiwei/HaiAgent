LongCLI HLD v8: rerun every confirmed 400-request stop
====================================================
Started 2026-10-22 23:55:35 Asia/Shanghai; supervisor PID 3328002.
Remote directory: /mnt/sdb/home/lizh639/longcli-hld-request400-rerun-20261022

Tasks: cmu15_445_p0, cmu15_445_p2, 61810_pgtbl, 61810_syscall, 61810_traps.
Selection evidence is preserved in selection-evidence.json. Syscall already
passed officially; it remains included because the user requested all tasks
that reached the 400-request ceiling. COW is already running in the separate
resource-match campaign and is not duplicated here.

Frozen HLD v8; fresh original starters and instructions, no hints or previous
solutions, original official grader unchanged. Old scores remain preserved.
800 total model requests / 32768 output / 128000 context / 32768 headroom;
600 tools / 7200 solver seconds / 2 CPU / 8 GiB per attempt.
Concurrency 3: P0, P2, Pgtbl started first; Syscall and Traps queued.
Each attempt <=24 CNY, maximum additional cost for these five <=120 CNY,
all auxiliary calls included, using the original shared 480 CNY ledger.
No automatic paid retries, GPT automations, or changes to other live jobs.

Preflight passed: original starter/image hashes and official grader AST,
test/parser hashes, source seals, request/output/monetary budget guards.
Actual entry probe made zero paid calls and rejected an isolated test
ledger before contacting the model.

Startup check at 23:56:23: all three active tasks had HTTP 200 responses
(P0 7, P2 9, Pgtbl 8), no HTTP/provider errors or budget stops. Effective
limits were recorded by the actual container entry. Shared ledger including
current reservations: 272.254487 CNY; remaining 207.745513 CNY.
