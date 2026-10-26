# Mechanism integration repair v1

Independent repair of frozen BestFGS 0.18.1 / HAI 0.8.2 and the HAI LHTB adapter.
Original releases and experiment results are not modified. This is a deployment
candidate, not a claim of improved task scores or a new benchmark result.

## Changes

- Adapter-provided cwd identity maps `/app` to the private workspace mirror and
  preserves subdirectory distinctions. Local non-Docker execution is unchanged.
- Over-budget HAI memory gets a compact prompt-only projection with conclusion,
  applicability, scope, validity, evidence IDs and excerpts. Full host memory and
  the existing 12000/3000-byte context/memory budgets are preserved.
- BestFGS uses a separate conservative diagnostic command classifier. Static
  `cd && read` chains and read pipelines are recognized; arbitrary scripts,
  substitutions, redirects, nested shells and known mutating forms are not.
  Output compression classification remains unchanged.
- Advisor and optional memory prompts declare the existing maximum of 3
  supporting evidence IDs. Validation still rejects unknown evidence, distinguishes
  count errors from unavailable evidence, and keeps the existing bounded budgets.
- HAI outcome classification ignores only known observability-only records between
  a terminal model error and deadline, preserves known provider errors, and reports
  explicit infrastructure-error endings as infrastructure failures.

## Validation

Local WSL tests passed: HAI 123; BestFGS lean and Docker 38; prompt views 20;
new repair regressions 9. Total 190 tests. The same 190 tests also passed in the
cloud Harbor runtime. Real cloud integration acceptance passed 13/13 on both
Ubuntu and the cached MATPOWER task image, with zero failures/errors and clean
resource cleanup. See `VALIDATION.md` and the workspace report at
`experiment_records/cloud-integration-repair-20260929/REPORT.md`.

`cloud_suite.py` adds a real Docker memory-intervention/reconsideration/follow-up
case. The former four-evidence acceptance check is explicitly corrected to verify
the declared maximum and accurate rejection, rather than requiring removal of
the existing safety limit. Valid three-evidence acceptance and unknown-ID rejection
remain tested. All other former acceptance requirements remain intact.

## Reproduction and provenance

`baseline-manifest.json` identifies the unchanged remote experiment sources.
`changed-sources.json` records the 8 modified production files and old/new hashes.
`fixed-source-manifest.json` verifies the repaired sources and copied test fixtures.
`release_tools.py` regenerates these last two manifests after an intentional edit.
Cloud tests verify both the repair manifest and that frozen source hashes remain
unchanged, then save a per-run copy of the test entry point.

Use the existing cloud Harbor Python runtime to run `cloud_suite.py`. Set
`INTEGRATION_IMAGE=zli12321/lhtb-matpower-opf-regression:20260615` for the cached
benchmark task image. No image pull, model API, benchmark grading, or changes to
existing trial containers occur. Each test run uses owned temporary resources and
keeps logs, prompts, manifests and mirrors after cleanup.

This package does not replace either frozen experiment's launch entry point.
Real-model performance validation requires a separate explicitly configured run.
