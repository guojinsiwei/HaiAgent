Recuris-Frozen / LongCLIBench FULL 20 / LARGE budget / fresh experiment

Remote: /mnt/sdb/home/lizh639/longcli-recuris-large20-20261009
Model: deepseek-flash, thinking disabled, temperature 0.
Resource profile EXACTLY follows longcli-recuris-taco-large7-20261009:
1,000,000 context allowance; 65,536 headroom; 32,768 output tokens;
800 actual API attempts (all roles and retries), 600 tools, 7200 seconds/task;
300 seconds/command; 2CPU / 8GiB / 256 PIDs; native 12-pair history policy.
No additional cost bar or new algorithmic gates. This is not full Recuris-TTA:
same frozen seed memory, task-local W goals/verification; Meta/TTA disabled.
Every task gets fresh workspace/container/home/tmp/shm; no prior trial cache.
All same pinned LongCLIBench 20 tasks including cow, lock, mmap and cmu_p2.
Existing 7 results NOT carried into this new full-20 experiment.

One included delivery canary (hog), then at most 6 concurrent tasks.
Automatic final-only official grading. Hidden tests never visible to solver.
Single task-local error does not stop healthy siblings. Existing engineering
guard pauses new admission after two consecutive identical infrastructure faults;
authentication/balance/cleanup failure pauses admission immediately.
No automatic paid task retry, no budget expansion, no email/GPT monitoring.
Source, resource protocol and zero-API acceptance are sealed before launch.
Launch: Start-Recuris-Large20.ps1; new key entered locally and hidden;
encrypted SSH stdin, RAM only, no reuse of any other experiment's credential.
Use status.py for public task counters and official scores, not process env.
