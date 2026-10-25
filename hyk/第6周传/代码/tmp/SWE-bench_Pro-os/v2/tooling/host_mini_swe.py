"""Host-side mini-swe-agent for Harbor: the LLM loop runs on the HOST, only bash
commands are exec'd into the sandbox. Consequences:

* the sandbox needs NO network at all -> tasks can set ``allow_internet = false``
  (Modal ``block_network=True``), closing the GitHub/goproxy/pypi leakage channel;
* no agent install step inside the sandbox (nothing to download);
* the API key never enters the sandbox.

Usage (from the harbor repo root)::

    PYTHONPATH=v2/tooling harbor run -p v2/tasks -e modal \
        -a host_mini_swe:HostMiniSweAgent \
        --model anthropic/claude-opus-5 \
        [--ak config_file=mini.yaml] [--ak step_limit=250] [--ak cost_limit=5]

Smoke test without an LLM: ``--model deterministic --ak deterministic_outputs_file=/path.json``
where the file holds a JSON list of ``{"role":"assistant","content":..., "extra":{"actions":[{"command":...}]}}``.
"""
from __future__ import annotations

import asyncio
import json
import platform
from pathlib import Path
from typing import Any

import yaml

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

_MARKER = "COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


class HarborSandboxEnvironment:
    """mini-swe-agent ``Environment`` backed by a Harbor ``BaseEnvironment.exec``."""

    def __init__(self, environment: BaseEnvironment, loop: asyncio.AbstractEventLoop,
                 *, cwd: str, env: dict[str, str], timeout: int):
        self._environment, self._loop = environment, loop
        self.cwd, self.env, self.timeout = cwd, dict(env), timeout

    def execute(self, action: dict, cwd: str = "", *, timeout: int | None = None) -> dict[str, Any]:
        from minisweagent.exceptions import Submitted

        command = action.get("command", "")
        t = timeout or self.timeout
        # exec is async on the harbor side; the agent loop runs in a worker thread.
        fut = asyncio.run_coroutine_threadsafe(
            self._environment.exec(command=command, cwd=cwd or self.cwd, env=self.env or None,
                                   timeout_sec=t),
            self._loop,
        )
        try:
            r = fut.result(timeout=t + 120)
            output = {"output": (r.stdout or "") + (r.stderr or ""), "returncode": r.return_code,
                      "exception_info": ""}
        except Exception as e:  # timeout etc. -> observation, not crash (mirrors DockerEnvironment)
            output = {"output": "", "returncode": -1,
                      "exception_info": f"An error occurred while executing the command: {e}",
                      "extra": {"exception_type": type(e).__name__, "exception": str(e)}}
        lines = output["output"].lstrip().splitlines(keepends=True)
        if lines and lines[0].strip() == _MARKER and output["returncode"] == 0:
            submission = "".join(lines[1:])
            raise Submitted({"role": "exit", "content": submission,
                             "extra": {"exit_status": "Submitted", "submission": submission}})
        return output

    def get_template_vars(self, **kwargs) -> dict[str, Any]:
        return {"cwd": self.cwd, "env": self.env, "timeout": self.timeout,
                **platform.uname()._asdict(), **kwargs}

    def serialize(self) -> dict:
        return {"info": {"config": {"environment": {"cwd": self.cwd, "env": self.env, "timeout": self.timeout},
                                    "environment_type": f"{self.__class__.__module__}.{self.__class__.__name__}"}}}


class HostMiniSweAgent(BaseAgent):
    SUPPORTS_ATIF = False

    def __init__(self, *args, config_file: str | None = None, cwd: str | None = None,
                 step_limit: int | None = None, cost_limit: float | None = None,
                 command_timeout: int | None = None, deterministic_outputs_file: str | None = None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._config_file = config_file or "mini"
        self._cwd = cwd
        self._step_limit = step_limit
        self._cost_limit = cost_limit
        self._command_timeout = command_timeout
        self._det_file = deterministic_outputs_file

    @staticmethod
    def name() -> str:
        return "host-mini-swe-agent"

    def version(self) -> str | None:
        import minisweagent
        return minisweagent.__version__

    async def setup(self, environment: BaseEnvironment) -> None:
        pass  # nothing to install in the sandbox

    async def _detect_cwd(self, environment: BaseEnvironment) -> str:
        r = await environment.exec(command="cd /app 2>/dev/null || cd /testbed 2>/dev/null || cd /; pwd")
        return (r.stdout or "/").strip().splitlines()[-1] if r.stdout else "/"

    def _build_model(self, model_cfg: dict):
        if self._det_file:
            from minisweagent.models.test_models import DeterministicModel
            return DeterministicModel(outputs=json.loads(Path(self._det_file).read_text()))
        from minisweagent.models import get_model
        return get_model(self.model_name, model_cfg)

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        from minisweagent.agents.default import DefaultAgent
        from minisweagent.config import get_config_path

        config = yaml.safe_load(get_config_path(self._config_file).read_text())
        agent_cfg: dict = dict(config.get("agent", {}))
        if self._step_limit is not None:
            agent_cfg["step_limit"] = int(self._step_limit)
        if self._cost_limit is not None:
            agent_cfg["cost_limit"] = float(self._cost_limit)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        agent_cfg["output_path"] = self.logs_dir / "mini-swe-agent.trajectory.json"

        cwd = self._cwd or await self._detect_cwd(environment)
        env_cfg = config.get("environment", {})
        sandbox = HarborSandboxEnvironment(
            environment, asyncio.get_running_loop(), cwd=cwd, env=env_cfg.get("env", {}),
            timeout=int(self._command_timeout or env_cfg.get("timeout", 60)),
        )
        model = self._build_model(config.get("model", {}))
        agent = DefaultAgent(model, sandbox, **agent_cfg)
        self.logger.info(f"host-mini-swe-agent: cwd={cwd} model={self.model_name} config={self._config_file}")
        result = await asyncio.to_thread(agent.run, instruction)
        (self.logs_dir / "result.json").write_text(json.dumps(
            {"exit_status": result.get("exit_status"), "n_calls": agent.n_calls, "cost": agent.cost}, indent=1))
        # Persist the model patch on the host side (before the verifier resets test files).
        r = await environment.exec(command=f"cd {cwd} && git add -A && git diff --cached", timeout_sec=120)
        (self.logs_dir / "model.patch").write_text(r.stdout or "")
        await environment.exec(command=f"cd {cwd} && git reset -q", timeout_sec=60)
        try:
            context.n_input_tokens = getattr(model, "n_input_tokens", None) or context.n_input_tokens
        except Exception:
            pass
