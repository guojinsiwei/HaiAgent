import argparse
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import sys

from .metrics import attach_evaluation, prepare_audit, summarize_manifest, summarize_run
from .model import APIClient
from .protocol import Config, Task
from .runtime import run
from .storage import atomic_json


def json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def parser():
    p = argparse.ArgumentParser(description="HAIAgent: linear CLI agent with bounded task memory")
    sub = p.add_subparsers(dest="action", required=True)
    r = sub.add_parser("run", help="run ONE task in an already isolated environment")
    r.add_argument("--task", required=True)
    r.add_argument("--config", required=True)
    r.add_argument("--out", required=True, help="new directory outside workspace")
    r.add_argument("--allow-local-execution", action="store_true",
                   help="acknowledge arbitrary model commands; this process is NOT a sandbox")
    d = sub.add_parser("demo", help="offline deterministic real-command demo; no API")
    d.add_argument("--out", required=True)
    a = sub.add_parser("audit-template", help="export method-blinded contextual audit evidence")
    a.add_argument("--run", required=True)
    a.add_argument("--out", required=True)
    e = sub.add_parser("attach-evaluation", help="import independently obtained evaluator result")
    e.add_argument("--run", required=True)
    e.add_argument("--report", required=True)
    s = sub.add_parser("summary")
    s.add_argument("--run", required=True)
    s.add_argument("--audit")
    c = sub.add_parser("compare")
    c.add_argument("--manifest", required=True)
    c.add_argument("--out")
    x = sub.add_parser("export-swe", help="export a submitted Git patch; does not run official evaluation")
    x.add_argument("--run", required=True)
    x.add_argument("--out", required=True)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.action == "run":
            if not args.allow_local_execution:
                p.error("Use an isolated disposable task environment and explicitly pass --allow-local-execution")
            task_path = Path(args.task).resolve()
            raw_task = json_file(task_path)
            raw_task["workspace"] = (task_path.parent / raw_task["workspace"]).resolve()
            raw_task["constraints"] = tuple(raw_task.get("constraints", []))
            task = Task(**raw_task)
            settings = json_file(args.config)
            transport = settings.pop("api")
            if set(settings) - {f.name for f in fields(Config)}:
                raise ValueError("Unknown run config fields")
            config = Config(**settings)
            key_name = transport.get("key_env", "HAI_API_KEY")
            key = os.environ.get(key_name, "")
            client = APIClient(transport["base_url"], transport["model"], key, config)
            result = run(task, config, client, args.out, secrets=(key,))
        elif args.action == "demo":
            from .demo import demo
            result = demo(args.out)
        elif args.action == "audit-template":
            bundle = prepare_audit(args.run, args.out)
            result = {"audit": args.out, "tool_calls": len(bundle["calls"]), "status": "requires_annotation"}
        elif args.action == "attach-evaluation":
            result = attach_evaluation(args.run, args.report)
        elif args.action == "summary":
            result = summarize_run(args.run, args.audit)
        elif args.action == "compare":
            result = summarize_manifest(args.manifest)
            if args.out:
                if Path(args.out).exists():
                    raise ValueError("Comparison output exists")
                atomic_json(args.out, result)
        else:
            from .metrics import load_run
            result, _ = load_run(args.run)
            if not result["submitted"] or result["artifact"]["kind"] != "git_patch":
                raise ValueError("No submitted Git artifact")
            patch = (Path(args.run) / result["artifact"]["path"]).read_bytes()
            if hashlib.sha256(patch).hexdigest() != result["artifact"]["sha256"]:
                raise ValueError("Artifact checksum mismatch")
            with Path(args.out).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps({"instance_id": result["task_id"], "model_name_or_path": "HAIAgent-" + result["method"],
                                         "model_patch": patch.decode("utf-8")}, ensure_ascii=False) + "\n")
            result = {"predictions": args.out, "status": "exported_not_evaluated"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.action == "run":
            return run_exit_code(result)
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"HAIAgent: {exc}", file=sys.stderr)
        return 2


def run_exit_code(result):
    """Submission is not evaluator success. Non-submission must not look healthy."""
    if result.get("submitted") and result.get("stop_reason") == "model_submit":
        return 0
    return {"api_error": 4, "infrastructure_error": 5, "protocol_error": 6, "interrupted": 130,
            "turn_budget": 3, "tool_budget": 3, "wall_budget": 3,
            "context_budget": 3, "stagnation": 3}.get(result.get("stop_reason"), 5)


if __name__ == "__main__":
    raise SystemExit(main())
