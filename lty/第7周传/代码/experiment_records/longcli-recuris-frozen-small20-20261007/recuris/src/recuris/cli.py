"""CLI checks are offline; tta/propose explicitly run only when invoked."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import importlib
import json
import os
from pathlib import Path
import sys

from . import __version__
from .audit import JsonlLogger, redact
from .client import ModelConfig, OpenAIChatClient
from .engine import RecurisConfig
from .evolution import EvolutionError, MetaAgent
from .memory import load_memory, load_seed, memory_digest, save_memory


def _temperature(value):
    return None if value.lower() == "null" else float(value)


def _model_args(parser):
    parser.add_argument("--model", default=None, help="Model ID; defaults to DEEPSEEK_MODEL or OPENAI_MODEL")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    parser.add_argument("--temperature", type=_temperature, default=0.0, help="0 by default; null omits unsupported sampling option")
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--meta-model", default=None, help="Optional fixed Meta-Agent model; default same as actor")
    parser.add_argument("--meta-max-seconds", type=float, default=600)
    parser.add_argument("--meta-max-calls", type=int, default=16)


def _chosen_model(args):
    envs = ("OPENAI_MODEL", "DEEPSEEK_MODEL") if args.api_key_env == "OPENAI_API_KEY" else ("DEEPSEEK_MODEL", "OPENAI_MODEL")
    model = args.model or next((os.environ[key] for key in envs if os.environ.get(key)), None)
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Pass --model or set the selected provider's model environment variable")
    return model


def _meta(args):
    model = ModelConfig(model_name=args.meta_model or _chosen_model(args), base_url=args.base_url,
                        api_key_env=args.api_key_env, temperature=args.temperature,
                        max_output_tokens=args.max_output_tokens)
    return MetaAgent(OpenAIChatClient(model), max_total_seconds=args.meta_max_seconds,
                     max_model_calls=args.meta_max_calls)


def _agent_kwargs(args):
    values = {"api_key_env": args.api_key_env, "temperature": args.temperature,
              "max_output_tokens": args.max_output_tokens}
    if args.base_url is not None:
        values["base_url"] = args.base_url
    for item in args.agent_kwarg:
        if "=" not in item:
            raise ValueError("--agent-kwarg requires key=value")
        name, raw = item.split("=", 1)
        if name in values:
            raise ValueError("Duplicate option; use the named model option instead of --agent-kwarg: " + name)
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        values[name] = value
    return values


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Recuris LongCLI adapter, task-local adaptation and validated memory admission")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("config", help="Print execution defaults; offline")
    seed = sub.add_parser("seed", help="Write neutral JSON memory; offline")
    seed.add_argument("--output", type=Path, required=True)
    seed.add_argument("--profile", choices=("neutral", "terminal"), default="neutral", help="terminal includes the authors' task-neutral closed-loop seed card")
    doctor = sub.add_parser("doctor", help="Check local configuration and adapter import; no network")
    doctor.add_argument("--model", default=None)
    doctor.add_argument("--api-key-env", default="DEEPSEEK_API_KEY")
    doctor.add_argument("--memory", type=Path, default=None)
    tta = sub.add_parser("tta", help="Run real official attempts; the experiment owner invokes this")
    _model_args(tta)
    tta.add_argument("--benchmark-root", type=Path, required=True)
    tta.add_argument("--task-id", required=True)
    tta.add_argument("--output-dir", type=Path, required=True)
    tta.add_argument("--mode", choices=("adaptation", "frozen"), default="adaptation")
    tta.add_argument("--attempts", type=int, default=4)
    tta.add_argument("--memory", type=Path, default=None)
    tta.add_argument("--seed-attempt-dir", type=Path, default=None)
    tta.add_argument("--agent-kwarg", action="append", default=[])
    tta.add_argument("--harness-timeout-seconds", type=float, default=3900)
    tta.add_argument("--process-timeout-seconds", type=float, default=4500)
    propose = sub.add_parser("propose", help="Generate a memory candidate from one sealed official failure (calls Meta-Agent)")
    _model_args(propose)
    propose.add_argument("--attempt-dir", type=Path, required=True)
    propose.add_argument("--output-dir", type=Path, required=True)
    propose.add_argument("--mode", choices=("cross_task", "tta"), default="cross_task")
    gate = sub.add_parser("admit", help="Offline gate over sealed source/dev attempts; no model or experiments")
    gate.add_argument("--base-memory", type=Path, required=True)
    gate.add_argument("--candidate", type=Path, required=True)
    gate.add_argument("--evaluations", type=Path, required=True)
    gate.add_argument("--split", type=Path, required=True)
    gate.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "config":
            print(json.dumps(asdict(RecurisConfig()), indent=2))
            return 0
        if args.command == "seed":
            if args.output.exists():
                raise ValueError("Output already exists; choose a new memory filename")
            save_memory(load_seed(args.profile), args.output)
            print(str(args.output.resolve()))
            return 0
        if args.command == "doctor":
            memory = load_memory(args.memory)
            report = {"python": sys.version.split()[0], "python_meets_longcli": sys.version_info >= (3, 12),
                      "model_configured": bool(args.model or os.environ.get("DEEPSEEK_MODEL") or os.environ.get("OPENAI_MODEL")),
                      "api_key_present": bool(os.environ.get(args.api_key_env, "").strip()),
                      "adapter_importable": False, "memory_digest": memory_digest(memory),
                      "skill_count": len(memory["E"]), "network_contacted": False,
                      "note": "Import does not verify benchmark checkout, Docker, dataset or endpoint compatibility."}
            try:
                adapter = importlib.import_module("recuris.longcli")
                report["adapter_importable"] = issubclass(adapter.RecurisAgent, adapter.BaseAgent)
            except ImportError:
                pass
            print(json.dumps(report, indent=2))
            return 0 if all(report[key] for key in ("python_meets_longcli", "model_configured", "api_key_present", "adapter_importable")) else 1
        if args.command == "tta":
            from .tta import TTAConfig, run_tta
            config = TTAConfig(benchmark_root=args.benchmark_root, task_id=args.task_id,
                model_name=_chosen_model(args), output_dir=args.output_dir, mode=args.mode,
                attempts=args.attempts, memory_path=args.memory, seed_attempt_dir=args.seed_attempt_dir,
                agent_kwargs=_agent_kwargs(args), harness_timeout_seconds=args.harness_timeout_seconds,
                process_timeout_seconds=args.process_timeout_seconds)
            meta = _meta(args) if args.mode == "adaptation" and args.attempts > 1 else None
            summary = run_tta(config, meta_agent=meta)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 1 if summary["status"] == "incomplete" else 0
        if args.command == "propose":
            from .tta import read_attempt
            attempt = read_attempt(args.attempt_dir)
            if attempt["success"] is not False:
                raise ValueError("Only an officially failed, completed attempt can be diagnosed")
            args.output_dir.mkdir(parents=True, exist_ok=False)
            logger = JsonlLogger(args.output_dir)
            try:
                candidate = _meta(args).propose(attempt["memory"], attempt["instruction"], attempt["trace"], mode=args.mode)
            except EvolutionError as exc:
                logger.save("error.json", {"error": str(exc), "model_calls": exc.model_calls,
                                          "input_tokens": exc.input_tokens, "output_tokens": exc.output_tokens})
                raise
            record = asdict(candidate)
            record.update(source_task_id=attempt["task_id"], source_attempt_dir=str(args.attempt_dir.resolve()))
            # This is gate input: changing a skill's text during log redaction
            # would invalidate candidate_digest and prevent later admission.
            (args.output_dir / "candidate.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
            save_memory(candidate.candidate_memory, args.output_dir / "memory.json")
            print(json.dumps({"candidate_digest": candidate.candidate_digest, "changed_components": candidate.changed_components,
                              "no_op": candidate.no_op, "output_dir": str(args.output_dir.resolve())}, indent=2))
            return 0
        if args.command == "admit":
            from .admission import admit_candidate
            report = admit_candidate(args.base_memory, args.candidate, args.evaluations, args.split, args.output_dir)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print("recuris: " + str(redact(str(exc))), file=sys.stderr)
        return 2
    return 2
