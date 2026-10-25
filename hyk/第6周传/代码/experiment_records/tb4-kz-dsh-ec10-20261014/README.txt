KZ + DSH 0.3.0 / TerminalBench 10-task candidate
Server: /var/tmp/lizh639-tb4-kz-dsh-ec10-20261014
Parent task selection: tb4-kz-dsh-unlimited-repair-20261014, first 10 frozen tasks.
No old scores are reused. Native DSH and standalone KZ campaigns are unchanged.

Model route: TaoToken Token Plan deepseek-flash, thinking disabled, temperature 0.
Context/output: 1,000,000 / 32,768 tokens, identical common config hash to parent.
Budget: no request/tool/cost cap; actual solver elapsed capped at 10,800 seconds.
Independent watchdog: kz-ec10-watchdog.service, scoped only to this campaign.
Concurrency: one paid pilot (first of ten); after valid engineering completion,
two simultaneous tasks. A zero benchmark score alone does not fail the pilot.
Original official verifier, task/user/resources; fresh task container/home/memory.
No automatic paid retry. Preflight-only retries retain separate receipts.
One non-pilot task error is isolated; confirmed credential failure pauses dispatch.

Candidate source archive SHA256:
afecb1ebd6b3d4b448e8ebfee2caa87e0771cc197ce7cc8fa6fb06b5584c7914
Algorithm behavior revision: evidence-control-1, rollback frozen.
External read-only artifact registry: /results; no change to DSH permissions.
No operator-complete requirement manifest is fabricated from model subgoals.

Acceptance:
- Linux: 362/362 offline tests, zero skipped, pinned DSH 0.2.0-rc.2.
- Headless DSH: five local simulated Messages cases passed, including malformed
  tool JSON recovery, forced compaction, KZ-loaded guard and request accounting.
- Official empty-solver installation/grading test: grade 0, no exceptions.
  A second absolute-path test verifies production-style artifact transfer.
- seal.py requires the second official receipt and scoped watchdog before final
  readiness. It simulates ten admissions and an isolated non-pilot failure.
These checks used no paid model API and are not model-performance results.

Launch only through Start-Secure.ps1 after seal.py succeeds.
The key is entered using getpass, transmitted on SSH stdin and retained only in
server process memory; never paste it in chat. No other experiment key is reused.
secure-input-status.json / launch-receipt.txt indicate input/launch acknowledgement.
Actual running state is determined by remote health.json, shared-state.json,
route status and tool progress, not merely the input-window acknowledgement.
