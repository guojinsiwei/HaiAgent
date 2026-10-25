"""Single-task DH worker with one documented format-only repair."""
import sys

import resume_worker
from cow_format_repair import install as install_reason_bound


def cow_trial(row, key, slot):
    from repair_runtime import install as install_existing_repairs
    from runner import run_trial

    assert row["method"] == "dh" and row["task"] == "61810_cow"
    install_existing_repairs("dh")
    install_reason_bound()
    run_trial(row, key)


resume_worker.trial = cow_trial

if __name__ == "__main__":
    key = sys.stdin.readline().strip()
    assert key and not any(char.isspace() for char in key)
    resume_worker.worker(key)
