"""Run benchmark host commands in WSL on Windows or directly on Linux.

This adapts the orchestration host only. Task containers still need a separate
backend; running the host inside a Notebook does not provide a Docker daemon.
"""

from __future__ import annotations

import sys


def linux_command(distro: str, *argv: str) -> list[str]:
    if sys.platform == "win32":
        return ["wsl.exe", "-d", distro, "--", *argv]
    if sys.platform.startswith("linux"):
        return list(argv)
    raise RuntimeError("BestFGS 评测主机需要 Linux 或 Windows/WSL")


def shell_command(distro: str, script: str) -> list[str]:
    return linux_command(distro, "bash", "-lc", script)


def default_docker_executable() -> str:
    if sys.platform == "win32":
        return r"C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    return "docker"
