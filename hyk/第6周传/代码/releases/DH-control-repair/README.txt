DH-control-repair — 2026-10-08

Frozen source candidate for a fresh, paired LongCLIBench20 tools/no-tools campaign.
Parent: DH-no-hard-stop plus the already tested tools-output-repair2 implementation.
Existing campaigns and scores are not modified or reused.

Fixed:
1. Recovery rejection count no longer terminates a task (original API/tool/time budgets remain).
2. Memory review metadata is recoverable; valid JSON key reordering is accepted.
3. One bounded retry per timeout increase and explicit external-condition recheck.
   Changed whole-workspace state is not overridden by a partial dependency cache.
4. TF-IDF similarity is advisory, not an execution veto. Exact unchanged-action guarding remains.
5. Narrow diagnostic recognition includes read chains, git observations and isolated Python probes.
   Recognition is not authorization or a sandbox escape.
6. Whole-workspace automatic rollback is deferred if other subgoal files changed or are unknown.
7. Source reads use exact byte-bounded pagination, not a 200-line rejection.
   Complete raw terminal capture is archived outside workspace; cleaned compact previews enter context.

Admission policy changed: this is not a claim of purely engineering-only or unchanged algorithm behavior.
Two fresh arms use identical source, shared context projection and fixed small budgets.
Only inspect_code/edit_code/verify_goal availability differs.
No route-search/prediction extension, larger model budget, cross-task memory or email is enabled.
