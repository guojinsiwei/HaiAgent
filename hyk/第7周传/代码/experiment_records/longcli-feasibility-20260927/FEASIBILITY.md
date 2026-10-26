# LongCLI-Bench: CubeStudio generation / separate official grading

Audit date: 2026-09-27. Upstream: https://github.com/finyorko/longcli-bench
Pinned commit: 2015f37b5c458f2562354de6b415e9182c91af64.

## Conclusion and scope

Source-level feasibility is positive for file-artifact generation on CubeStudio,
followed by grading in fresh official Docker images on the college node or local Docker.
This is NOT yet an end-to-end validated deployment or an official leaderboard-equivalent
execution environment. No model calls, package installations or experiment launches made.

## Verified evidence

- Inspected all 20 real task Dockerfiles, Compose files, task.yaml and run-tests.sh;
  excluded terminal-bench_task scaffold. All stage task files under /app.
- Five cs61 Python/Scheme tasks; five C/C++ tasks (two ap1400, three cmu15_445);
  ten 61810 xv6/RISC-V tasks. No privileged/devices/network_mode/cap_add declarations
  found in inspected Compose files.
- All 20 run-tests.sh pass bash -n on CubeStudio. This checks syntax only, not grading
  correctness. Some scripts contain uncommented prose and must be exercised unchanged
  before claiming that grading succeeds.
- Official harness _run_tests installs/injects test assets and executes run-tests.sh;
  _parse_results uses the task parser. TB_SKIP_AGENT only skips inference: it does NOT
  import an external submission. TB_SAVE_APP_RESULT exports /app late in the lifecycle.
- Several test scripts copy hidden tests into the project and later delete files/build
  directories. A submitted artifact must be frozen BEFORE grading, not exported afterward.
- Task budgets: 18 tasks 7200 seconds; ap1400 tasks 10800 seconds. This is budget, not
  proof every task requires that long. Test timeouts vary (300/720/1800 seconds).
- Representative 61810_cow Makefile uses qemu-system-riscv64 with -machine virt, software
  machine emulation options and user-mode networking, without explicit KVM requirement.
  This does not yet prove all ten tasks run on CubeStudio.
- Previous cgroup checks: each CubeStudio has 10 CPU and 16,000,000,000-byte memory limit.
  Current first-container check: Ubuntu 22.04, GCC 11.4; CMake, clang-15, RISC-V GCC,
  qemu-system-riscv64 and uv were not found on PATH. Official base uses Ubuntu 24.04.

## Proposed execution contract

1. Pin task source, image digests, toolchains, task list, model and all budgets.
2. Construct clean task-only inputs in an isolated location. Never ship official tests,
   reference solutions, previous outputs or controller credentials to agent workspaces.
3. Keep toolchain/process namespace isolated, with reset per task/method. A directory or
   venv alone is not an isolation boundary. Confirm filesystem/namespace options before
   allowing generated shell commands near existing shared /mnt experiments.
4. Freeze pre-evaluation source changes, including additions, deletions, permissions and
   safe links, as a content-hashed artifact. Do not blindly overlay stale build products,
   test_output, caches or virtualenvs. Preserve original artifact separately.
5. Start a fresh official task image at the grading node. An explicit artifact-import
   adapter restores the permitted source delta before official test injection. Do not
   treat TB_SKIP_AGENT as this adapter. Rebuild binary outputs in the scoring environment.
6. Execute unchanged official test scripts and parser. Record F2P, P2P, all_is_pass,
   step scores, logs and infrastructure errors. Do not trust submitted score files.
7. For a single-final-grading protocol, do not give official feedback during solving.
   Label this separately from upstream multi-turn test-feedback settings. Keep all arms
   under the same setting; maintain independent generation-time and scoring-time logs.

## Remaining acceptance gates (no paid run until satisfied)

- Reproduce a clean task's public build/run checks on CubeStudio for each intended family.
- Validate compilation/QEMU and resource limits; stop on nonportable requirements.
- Use the same frozen artifact for direct official grading and transfer/replay grading;
  require identical parsed scores and test coverage. Include unchanged/invalid artifacts
  and an evaluator-only known-good fixture. Never expose its solution to agents.
- Check safe import, clean reset, task boundary isolation, hidden-test separation and
  timeout handling. For graph search, validate restoration of generated build/state files.
- Prefer the college node for final grading after checking its live workload/storage;
  local Docker remains a fallback, not a necessary generation dependency.

Recommendation: start acceptance with a Python/Scheme task and a C++ task; then validate
xv6/QEMU. Do not silently select only tasks whose Raw outcomes favor the proposed method.

## Executed portability probe (2026-09-27)

- Zero model/API calls; no changes to running experiments.
- Task-only sources uploaded to CubeStudio at /mnt/lizh639/longcli-portability-20260927.
- System Python venv creation failed (missing ensurepip). A separate runtime2 was
  successfully created with the existing Python 3.11 interpreter; CMake 3.28.4 installed
  there, without changing system packages or the existing environment.
- Scheme `python3 -B scheme.py --help`: exit 0. This checks startup, not task solution.
- C++ official CMake configuration: exit 1 because the initial project has no `test/`
  directory, which its CMakeLists unconditionally references. Hidden evaluation tests
  were deliberately not transferred. No complete project build is claimed.
- A direct C++17 compilation of src/primer/trie.cpp with the shipped include/fmt
  paths succeeded using CubeStudio GCC 11.4 (exit 0). This is only one source object.
- All 1,496 file/link content entries matched between uploaded archive, remote
  manifest and returned archive. Source was unchanged. Permissions and functional
  grading equivalence are not established by this content comparison.
- Local official Dockerfile builds were started under longcli-audit/* tags; dependency
  downloads are still in progress. Official grading replay has NOT completed.

Evidence: cube-result.json, roundtrip-result.json, cube_probe.py, verify_roundtrip.py.
Conclusion: source transport and basic language execution work; full split execution
is NOT yet accepted. C++ public build adaptation and official grading replay remain gates.

## Follow-up fixes and replay (2026-09-27 afternoon)

- Added public_build_probe.py: copies the public C++ project into a unique disposable
  mirror, guards only the missing test/CMakeLists.txt inclusion, and builds there.
  Original submission CMakeLists.txt is asserted byte-identical. No hidden tests copied.
  Configure and all bustub_primer objects succeeded (2.17 s and 3.58 s respectively).
  This is a source-only build adapter, not a replacement for official evaluation.
- Both upstream Dockerfile builds completed locally under longcli-audit/* tags.
  Recorded image IDs: make-pytest = sha256:5568ac38fe7ad7bf91717543babf5852819736facbb067f3889788c45b8f0fea;
  c-env = sha256:f9e91b60e8188c4adb8d590d2945cfdff8c061976c5b154f504117faf9393b21.
- Added replay_probe.py: fresh resource-limited containers, explicit source archive
  import, unchanged task tests/run-tests.sh, then actual upstream pytest metric helper.
  Containers have no host mounts or credentials and are stopped after each check.
- Scheme direct vs Cube-returned source: script exits 0; F2P 0.0 and P2P 1.0 with
  identical per-test results. Full evidence in replay-20260927-153425/result.json.
  An unfinished starter scoring zero is expected; this is not a model experiment.
- Important upstream behavior: LongCliParser itself always returns PASSED. Never use
  this placeholder as task success; use actual F2P/P2P metrics and test coverage.
- C++ two-way official replay started separately using --cpp, capped at the task's
  720 s scoring limit per run. Results must be inspected before declaring acceptance.
- C++ replay subsequently completed successfully in both directions: script exit 0,
  F2P 0.0, P2P 1.0 (8 collected P2P entries), equal parsed metrics/per-test P2P maps.
  Evidence: replay-cmu15_445_p0-20260927-153550/result.json and each test_output folder.
  Thus both starter-source round trips are validated; this does not establish correct
  grading of every possible edited artifact or all LongCLI task families.
- A nonzero known-good solution fixture, task-boundary isolation and xv6/QEMU support
  remain unvalidated. The upstream Scheme solution.sh is empty, so it cannot serve
  as a known-good oracle. No mass model experiment is authorized by these probes.

## Raw-3 acceptance and deployment (2026-09-27)

- Added evaluator-only Frame fixture from its public contract: partial F2P 1/28,
  versus incorrect lookup F2P 0. Both preserve all 53 P2P checks. Deliberately modifying
  a protected file is rejected by P2P. Evidence is consolidated in
  ../longcli-raw3-20260927/acceptance.json. This is not a full-task gold solution.
- Bubblewrap mount operations are denied on CubeStudio. A tested alternative uses
  host UID 65534, new user/PID/network namespaces, a private exported image root,
  chroot followed by capability removal and no_new_privs. System/root ownership is
  not granted to the task UID. Twelve isolation checks passed, including prevention
  of workspace-root replacement. No host proc, secrets, Docker socket or tests exposed.
- Scheme/Ants/Cats each passed an isolated scripted read/submit fixture with zero
  API calls. Raw method uses the frozen HAI runtime without its memory component.
- Ready deployment: /mnt/lizh639/longcli-raw3-20260927, cubestudio_container.
  Sequential three tasks, task limit 7200 s. See its protocol.json and README.md for
  network/background-process restrictions and bounded audit output.
- At deployment acceptance no paid run has started: a fresh private API-key input
  is required through Start-LongCLIRaw3.ps1. Do not mine another run's credentials.
- This closes basic positive/negative scoring and isolation gates for this subset,
  not xv6/QEMU or a benchmark-wide reproducibility claim.
