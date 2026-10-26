"""Raw model + CLI: same v12 executor, budgets and delivery, without memory/search."""
from __future__ import annotations

import logging

from .__main__ import build_parser
from .evidence_runtime import SYSTEM_PROMPT, parse_decision, run_evidence, run_from_args
from .retrac_adapter import OpenAICompatibleJSONClient


def parse_turn(payload, config):
    commands, verification, done, _ = parse_decision(payload, config)
    return commands, verification, done


def run_raw(task, environment, client, config, *, max_iterations, max_tool_calls, max_commands):
    return run_evidence(task, environment, client, config, max_iterations=max_iterations,
                        max_tool_calls=max_tool_calls, max_commands=max_commands,
                        memory_enabled=False, branching_enabled=False, blocking_memory_mode="off")


def main(argv=None):
    parser = build_parser()
    parser.description = __doc__
    parser.set_defaults(no_adaptive_budget=True, budget_multiplier=1.0,
                        experience_mode="off", disable_evidence_branching=True, blocking_memory="off")
    args = parser.parse_args(argv)
    if args.engine != "evidence":
        parser.error("v12 Raw uses --engine evidence with all search/memory disabled; use the frozen v10 release for historical Raw")
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(asctime)s | %(message)s", datefmt="%H:%M:%S", force=True)
    return run_from_args(args, parser, raw=True, client_factory=OpenAICompatibleJSONClient)


if __name__ == "__main__":
    raise SystemExit(main())
