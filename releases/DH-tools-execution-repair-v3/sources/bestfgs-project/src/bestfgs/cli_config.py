"""The API transport configuration shared by BestFGS and the raw CLI baseline."""
from .retrac_adapter import RetracModelConfig


def model_config_from_args(args):
    return RetracModelConfig.from_environment(
        provider=args.provider, model_name=args.model, base_url=args.base_url,
        api_key_env=args.api_key_env, temperature=args.temperature, top_p=args.top_p,
        reasoning_effort=args.reasoning_effort, solve_reasoning_effort=args.solve_reasoning_effort,
        timeout_seconds=args.model_timeout, max_wall_time_seconds=args.model_max_wall_time,
        request_attempts=args.model_request_attempts, parse_attempts=args.model_parse_attempts,
        retry_interval_seconds=args.model_retry_interval, max_retry_interval_seconds=args.model_max_retry_interval,
        use_json_response_format=not args.no_json_response_format,
        max_commands_per_action=args.max_commands_per_action,
    )
