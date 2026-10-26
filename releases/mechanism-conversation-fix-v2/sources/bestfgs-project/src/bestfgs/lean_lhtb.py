"""Explicit opt-in bridge for a future frozen LHTB protocol (not a launcher)."""
from dataclasses import replace
import time
from .lean_docker import ContinuousDockerEnvironment
from .lean_protocol import LeanConfig
from .lean_runtime import LeanTaskRunner


def run_lhtb(state, task, action_client, advisor_client, output, *, feedback=None, config=None):
    """Reuse owned DockerState and binary continuation, with cumulative budgets.

    The parent Harbor adapter retains resource, verifier, cleanup and outer
    deadline responsibilities. This bridge cannot resume old search checkpoints.
    """
    remaining = state.deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError('LHTB work deadline already exhausted')
    config = config or LeanConfig()
    config = replace(config, wall_seconds=min(config.wall_seconds, remaining))
    environment = ContinuousDockerEnvironment(state)
    try:
        remaining = state.deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('LHTB work deadline exhausted during environment setup')
        config = replace(config, wall_seconds=min(config.wall_seconds, remaining))
        return LeanTaskRunner(environment, action_client, advisor_client, config,
                              output, submission_feedback=feedback).run(task)
    finally:
        environment.close()
