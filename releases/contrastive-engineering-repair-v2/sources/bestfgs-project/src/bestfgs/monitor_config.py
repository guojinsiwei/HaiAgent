"""Explicit same-model default or independent low-cost monitor configuration."""
from dataclasses import replace
from .retrac_adapter import RetracModelConfig


def monitor_config(base, *, model_name=None, provider=None, base_url=None, api_key_env=None):
    if (provider or base_url) and not model_name:
        raise ValueError('changing monitor provider/endpoint requires an explicit monitor model')
    if provider or base_url or api_key_env:
        config = RetracModelConfig.from_environment(provider=provider or base.provider,
            model_name=model_name or base.model_name,
            base_url=base_url or (base.base_url if not provider or provider == base.provider else None),
            api_key_env=api_key_env,
            temperature=0)
    else:
        config = replace(base, model_name=model_name or base.model_name)
    return replace(config, max_tokens=1536, thinking_enabled=False, temperature=0,
                   request_attempts=1, parse_attempts=1, timeout_seconds=30, max_wall_time_seconds=45)
