"""Read-only Notebook checks; never call a model, pull images, or expose keys."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def inspect_environment(workspace: Path | None = None) -> dict:
    linux = sys.platform.startswith("linux")
    python_ok = sys.version_info >= (3, 11)
    tools = {name: shutil.which(name) for name in ("bash", "git", "ssh", "docker", "harbor")}
    workspace_ok = workspace is None or workspace.is_dir()
    return {
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "tools": tools,
        "workspace": str(workspace.resolve()) if workspace is not None else None,
        "workspace_exists": workspace_ok,
        "credential_present": {
            name: bool(os.environ.get(name, "").strip())
            for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY")
        },
        "agent_runtime_ready": linux and python_ok and bool(tools["bash"]) and workspace_ok,
        "task_backend_status": "pending_college_notebook_connection_and_image_permissions",
        "official_benchmarks_ready": False,
        "notes": [
            "只检查 Agent 的基础运行环境，不检查任务依赖或模型网络连通性。",
            "docker 命令存在不代表 Docker 服务可用；本检查不会启动或连接 Docker。",
            "每题 Notebook 创建、环境初始化及官方评测后端尚待学院平台信息。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BestFGS Notebook 只读环境检查（不调用 API）")
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    report = inspect_environment(args.workspace)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["agent_runtime_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
