# SWE-bench Pro V2

V2 is the validated public split of SWE-bench Pro: **642 tasks across 11 repositories**, each shipped here as a
self-contained [Harbor](https://github.com/laude-institute/harbor) task directory with its verifier, reference
solution and public container image, plus the **HARD-51** subset and the tooling for the locked evaluation protocol.
The same data is on HuggingFace as `ScaleAI/SWE-bench_Pro` (config `default` = V2, `hard` = HARD-51, `v1` = the
original 731 tasks).

## Layout

```
v2/tasks/<instance_id>/            642 Harbor tasks
  instruction.md                   what the agent sees: PR description, requirements, new interfaces
  task.toml                        Harbor config: image, timeouts, [agent] network_mode = "no-network"
  environment/Dockerfile           FROM ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>
  solution/gold_patch.diff, solve.sh   reference solution (used by `-a oracle`)
  tests/test.sh, run_script.sh, parser.py, config.json, test_patch.patch   verifier
v2/hard51_ids.txt                  the HARD-51 subset (one instance_id per line)
v2/tooling/                        locked-protocol agents, fresh-sandbox re-grader, probes (see below)
v2/GATE.md                         release-gate results for this exact tree
v2/SHA256SUMS                      checksums of every file under v2/ (`cd v2 && shasum -a 256 -c SHA256SUMS`)
```

Images are public: `docker pull ghcr.io/scaleapi/swe-bench_pro-v2:<instance_id>` (linux/amd64, anonymous). The
repository is at `/app` (a few tasks use `/testbed`), checked out at the task's base commit with a sanitised git
history (no fixing commit, stray refs, stashes or hooks).

## Running

Install Harbor with Modal support (Modal >= 1.5.1 is needed for the per-phase network policy):

```bash
uv tool install 'harbor[modal]>=0.22' && modal setup
git clone https://github.com/scaleapi/SWE-bench_Pro-os && cd SWE-bench_Pro-os
```

Sanity check (reference patch resolves every task; empty patch resolves none):

```bash
harbor run -p v2/tasks -e modal -n 50 -a oracle --job-name sbp-v2-oracle
harbor run -p v2/tasks -e modal -n 50 -a nop    --job-name sbp-v2-nop
```

Evaluate a model under the locked protocol (example: Claude Code):

```bash
export ANTHROPIC_API_KEY=...
PYTHONPATH=v2/tooling harbor run -p v2/tasks -e modal -n 50 \
  -a locked_claude_code:LockedClaudeCode -m anthropic/<model> \
  --ak reasoning_effort=high --ak disallowed_tools=WebFetch,WebSearch \
  --allow-agent-host api.anthropic.com --job-name sbp-v2-<model>

# authoritative score: re-grade every captured diff on a pristine image
PYTHONPATH=v2/tooling harbor run -p v2/tasks -e modal -n 50 \
  -a patch_replay:PatchReplayAgent -m replay --ak source_job=jobs/sbp-v2-<model> --job-name sbp-v2-<model>-regrade
```

`locked_mini_swe:LockedMiniSwe` (mini-swe-agent, `--ak config_file=v2/tooling/configs/mini_toolcall.yaml`) and
`locked_codex:LockedCodex` (Codex CLI, `--ak config=v2/tooling/configs/codex_config.toml`) work the same way; point
them at any OpenAI-compatible endpoint with `--ae OPENAI_API_KEY=... --ae OPENAI_API_BASE=...`.

HARD-51 only:

```bash
harbor run -p v2/tasks $(sed 's/^/-i /' v2/hard51_ids.txt) -e modal -n 20 -a <agent> ...
# or materialise it as its own dataset directory
python3 v2/tooling/make_subset.py v2/tasks v2/hard51_ids.txt datasets/hard51
```

## The locked protocol

1. **Agent phase is offline.** `[agent] network_mode = "no-network"` in every `task.toml`; `--allow-agent-host`
   whitelists only the model endpoint. Web-fetch tools are disabled (`--ak disallowed_tools=WebFetch,WebSearch`).
   The setup and verifier phases keep normal access (a few Go tasks fetch modules at test time).
2. **The verifier never runs in the agent's sandbox.** The locked agents capture the agent's `git diff` as
   `model.patch`; `patch_replay:PatchReplayAgent` applies it to a pristine image and runs the unchanged verifier.
   Report the re-graded number; publish both.
3. **50-minute budget per task** (in-sandbox `timeout`, so a partial patch is still captured and graded).
4. **Probe before you trust.** `v2/tooling/probe/make_probe_task.py` turns any task into a network probe or a
   git-history probe whose "solution" prints what the sandbox can reach or see; run it with `-a oracle`.

## HARD-51

The 51 tasks failed by at least two of five model families (Claude Opus 5, GLM-5.3, Kimi-K3, Inkling, Gemini 3.8
Flash) under this protocol, minus three tasks later found ambiguous. Every one of them passes with the reference patch
and fails with an empty patch. Scores on it separate frontier models far better than the full set does.

## Release gate for this tree

| Check | Result |
|---|---|
| Reference patch (`-a oracle`) | **642 / 642** tasks resolved |
| Empty patch (`-a nop`) | **642 / 642** tasks unresolved (0 spurious passes) |
| Images | `ghcr.io/scaleapi/swe-bench_pro-v2`, pulled anonymously; 642 manifests verified, 211 rebuilt images digest-identical to the graded originals |
| Infrastructure retries | oracle 3 trial(s), empty-patch 3 trial(s) hit Modal sandbox errors on the first pass and passed on re-run (no task-level failures) |

## What changed from v1

- 731 -> 642 tasks: 89 dropped after review. Same repositories, same base commits.
- Instructions: 529 problem statements rewritten so that every graded assertion traces back to a sentence in the
  text (only problem statement, requirements and interfaces changed); each correction was implemented blind by a
  second engineer and graded by the task's own hidden tests.
- Verifier (all 642): hidden-test paths are restored or removed before the test patch is applied; agent edits to
  fixtures and snapshots are reverted; stale Python bytecode is purged; a leftover git index lock no longer makes
  restores fail silently. Test lists regenerated against repaired parsers; 214 test patches and 38 gold patches revised.
- Images: rebuilt from sanitised bundles and published on GHCR; 211 images received dependency fixes.

`tests/config.json` in the task directories is exactly the file the verifier was graded with (some list values are
stored as Python-literal strings; `tests/test.sh` accepts both). The HuggingFace columns are normalised to strict JSON.

## The v1 pipeline

`swe_bench_pro_eval.py`, `run_scripts/`, `dockerfiles/`, the Docker Hub images (`jefzda/sweap-images`) and the
`dockerhub_tag` column belong to the v1 release and are kept for reproducing v1 numbers (HuggingFace config `v1`,
tag `v1.0`). They are not used by V2.

## Citation

```bibtex
@article{deng2025swebenchpro,
  title={SWE-Bench Pro: Can AI Agents Solve Long-Horizon Software Engineering Tasks?},
  author={Deng, Xiang and Da, Jeff and Pan, Edwin and Sun, Yannis Yiming and Wu, Chen Bo Calvin and Bhutani, Sanyam and others},
  journal={arXiv preprint arXiv:2509.16941},
  year={2025}
}
```
