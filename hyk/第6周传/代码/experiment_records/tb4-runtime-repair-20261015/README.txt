2026-10-15 isolated engineering repair (original experiments remain stopped)

Local source: experiment_records/tb4-runtime-repair-20261015
Server source: /mnt/sdb/home/lizh639/tb4-runtime-repair-20261015
Original source/results are not overwritten. This candidate has not made paid
model calls and has not restarted or reconciled the stopped 30+30 campaign.
Its campaign files are a deployable template, not a claim that the remaining
tasks have been resumed. Existing admissions must be explicitly reconciled
before any future continuation; do not launch this as an unnoticed fresh 60.

Fixed:
- Parse provider error codes, including QUOTA behind HTTP 429 or HTTP 200 SSE.
- Latch quota/credentials per task so every later role avoids an outbound request.
- Persist availability receipts; scheduler observes running as well as finished
  trials, pauses both arms on provider quota, and retains pending tasks.
- Temporary 429/5xx use 5/10/20/.../60 second backoff, respecting Retry-After.
  This changes transport behavior only, not strategy/action budgets.
- DSH exposes only complete SSE responses. One retry is allowed before any
  model output/tool action is delivered; every actual HTTP attempt is audited.
- Native restore/checkpoint actions are rejected before file operations. Panel
  and prompt expose the frozen capability. Environment.restore also refuses.
- Supplied Harbor skills are declared and their paths are made discoverable to
  both agent arms. Read-only task working directories are allowed; harness-owned
  instruction files live in writable agent logs. Original task user is retained.
- Transient image build network failures retry with waits within the original
  Harbor build deadline; dependency failures and scoring are not blindly retried.
- Finish unpaid installation/runtime checks across the batch before paid work.
  Do not grade intentionally unfixed code as an installation acceptance test.
  Paid runs retain the official verifier and its timeout unchanged.

Tests:
accept.py runs native scripted-loop/real-loopback-HTTP regressions, real scheduler
fault simulations, Harbor skills contract checks, DSH SSE/quota tests, deadlines.
container_smoke.py runs the native fixtures/tests inside a cached official task
image as uid/gid 65534, with /app read-only and external networking disabled.
acceptance.json and container-smoke.json are the authoritative test receipts.

Not claimed fixed:
- FreeCAD official verifier dependency conflict (pip versus conda-provided VTK).
  Changing the official grading environment requires a separately validated,
  declared dependency repair shared by both arms. No hidden scoring patch added.
  environment-blockers.json prevents either arm from spending model quota on
  this known-ungradable environment before that repair has been validated.
- External registry/network availability and actual TaoToken quota/billing.
- End-to-end paid-provider behavior after quota replenishment.

2026-10-15 spending update:
- Authorized cap: 30 CNY package-equivalent value for BOTH arms combined.
  89.90 CNY / 100,000,000 tokens -> cap 33,370,411 total input+output tokens.
  This is consumption of a prepaid package, not a second payment or the provider's
  retail on-demand bill. Cached input is included in this uniform package rate.
- spending.sqlite records every HTTP attempt, including action/advisor/monitor/
  critic, DSH compaction and retries. Atomic reservations cover concurrent work.
  The immutable profile and debits survive restart. No silent balance reset.
- Each call reserves the model's 1,048,576 input-token ceiling plus max_tokens;
  actual final usage releases the unused portion. The run may stop up to about
  one reservation (1.08M tokens, roughly 0.97 yuan) before the nominal cap.
- Missing final usage or an interrupted ledger leaves the reservation charged
  conservatively and pauses paid admission for reconciliation; never assume zero.
- Budget refusal occurs BEFORE provider HTTP. Existing artifacts remain available
  for official grading. Spending stops are not automatically retried as failures.
- The ledger uses a private Docker bridge endpoint and an in-memory authorization
  token. It stores task IDs and counts only, never API keys or prompt contents.
- Endpoint/model are pinned to Tianyi's purchased package: ai.ctaigw.cn/v1/messages,
  deepseek-v4-flash-0428. A different provider/model is blocked before HTTP.
- Tianyi activation, a fresh hidden APP Key input, provider compatibility/usage
  verification and provider-acceptance.json are required before launch.
  No paid request, activation, automatic top-up or experiment restart was performed.
- The common 3-hour solver limit remains. Request/tool counters remain uncapped
  individually; the common monetary/token budget is now the spending boundary.
No ordinary score-zero task is converted into an automatic algorithm retry.
