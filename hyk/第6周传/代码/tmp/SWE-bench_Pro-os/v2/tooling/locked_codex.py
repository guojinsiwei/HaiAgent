"""Codex CLI (upstream harbor agent) under the locked protocol.

Differences from the built-in ``codex`` agent:
  * install(): uploads a pinned standalone musl binary (tooling/bin/codex-slim-0.155.1.tar.gz: codex + codex-code-mode-host + rg
    from codex-package-x86_64-unknown-linux-musl, rust-v0.155.1) from the host instead of nvm/npm — no network needed in the sandbox, no Node.
  * exec_as_agent(): wraps the `codex exec` invocation in an in-sandbox `timeout` (budget - 60 s) so the process
    always ends and the patch can be captured even if the client-side timeout cannot cancel a stalled stream.
  * run(): always writes the repo's git diff to /logs/agent/model.patch for fresh-sandbox re-grading.
"""
from __future__ import annotations
import shlex
from pathlib import Path
from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_TARBALL = Path(__file__).parent / "bin" / "codex-slim-0.155.1.tar.gz"  # bin/codex, bin/codex-code-mode-host, codex-path/rg from codex-package-x86_64-unknown-linux-musl (rust-v0.155.1)
_CAPTURE = (
    "mkdir -p /logs/agent; "
    "repo=$(git -C /app rev-parse --show-toplevel 2>/dev/null || git -C /testbed rev-parse --show-toplevel 2>/dev/null || echo /app); "
    'cd "$repo" && git add -A 2>/dev/null; git diff --cached > /logs/agent/model.patch 2>/dev/null; git reset -q 2>/dev/null; '
    "wc -c < /logs/agent/model.patch; true"
)

class LockedCodex(Codex):
    @staticmethod
    def name() -> str:
        return "codex-locked"

    _URL = "https://github.com/openai/codex/releases/download/rust-v0.155.1/codex-package-x86_64-unknown-linux-musl.tar.gz"
    _SHA = "a65b895c6ac1a73629bbe4b864640c86133e94a43b4d67b3103044e1a306d5a2"
    _EXTRACT = ("cd /tmp && rm -rf codexpkg && mkdir codexpkg && tar xzf codex.tar.gz -C codexpkg bin/codex bin/codex-code-mode-host codex-path/rg "
                "&& install -m 755 codexpkg/bin/codex codexpkg/bin/codex-code-mode-host /usr/local/bin/ "
                "&& { command -v rg >/dev/null 2>&1 || install -m 755 codexpkg/codex-path/rg /usr/local/bin/rg; } "
                "&& rm -rf codex.tar.gz codexpkg && codex --version && ls /usr/local/bin/codex-code-mode-host")

    async def install(self, environment: BaseEnvironment) -> None:
        """Setup phase has network (verified by the Claude Code bootstrap install under the same flags), so fetch the
        pinned release inside the sandbox (fast, no host upload); verify sha256; fall back to uploading the slim tarball."""
        url, sha = self._URL, self._SHA
        fetch = (
            "set -e; cd /tmp && rm -f codex.tar.gz; "
            f"if command -v curl >/dev/null 2>&1; then curl -fsSL --retry 3 -m 240 -o codex.tar.gz {url}; "
            f"elif command -v wget >/dev/null 2>&1; then wget -q -T 240 -t 3 -O codex.tar.gz {url}; "
            f"elif command -v python3 >/dev/null 2>&1; then python3 -c 'import urllib.request,sys; urllib.request.urlretrieve(sys.argv[1], \"codex.tar.gz\")' {url}; "
            "elif command -v apt-get >/dev/null 2>&1; then (apt-get update -qq && apt-get install -y -qq curl) >/dev/null 2>&1 && "
            f"curl -fsSL --retry 3 -m 240 -o codex.tar.gz {url}; "
            "else echo NO_DOWNLOADER; exit 3; fi; "
            f"echo '{sha}  codex.tar.gz' | sha256sum -c - && echo FETCHED")
        r = await environment.exec(command=fetch, user="root", timeout_sec=280)
        if r.return_code != 0 or "FETCHED" not in (r.stdout or ""):
            self.logger.warning(f"in-sandbox fetch failed (rc={r.return_code}): {(r.stderr or '')[:200]} — falling back to upload")
            await environment.upload_file(_TARBALL, "/tmp/codex.tar.gz")
            extract = self._EXTRACT.replace(" bin/codex bin/codex-code-mode-host codex-path/rg", "")  # slim tarball has only these
        else:
            extract = self._EXTRACT
        r = await environment.exec(command="set -e; " + extract, user="root", timeout_sec=120)
        self.logger.info(f"codex install: rc={r.return_code} {(r.stdout or '').strip()} {(r.stderr or '').strip()[:200]}")
        if r.return_code != 0:
            raise RuntimeError(f"codex install failed: {r.stderr}")

    async def exec_as_agent(self, environment, command: str, **kw):
        if "codex exec" in command:
            budget = int(getattr(self, "_timeout_sec", None) or 3000) - 60
            command = f"timeout -k 30 {budget} bash -c {shlex.quote(command)}"
        return await super().exec_as_agent(environment, command, **kw)

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        try:
            await super().run(instruction, environment, context)
        finally:
            try:
                r = await environment.exec(command=_CAPTURE, user="root", timeout_sec=300)
                self.logger.info(f"model.patch bytes: {(r.stdout or '').strip()}")
            except Exception as e:
                self.logger.warning(f"patch capture failed: {e}")
