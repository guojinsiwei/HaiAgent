"""Independent role configuration with explicit endpoint/credential selection."""
from dataclasses import replace
from .retrac_adapter import RetracModelConfig


def collaborator_config(base, role, *, model_name=None, provider=None, base_url=None, api_key_env=None):
    if role not in {'advisor','monitor'}:
        raise ValueError('unknown collaborator role')
    changed_endpoint=((provider is not None and provider!=base.provider)
                      or (base_url is not None and base_url.rstrip('/')!=base.base_url.rstrip('/')))
    if changed_endpoint and not (model_name and api_key_env):
        raise ValueError('changing '+role+' endpoint/provider requires explicit model and credential variable')
    if api_key_env or changed_endpoint:
        config=RetracModelConfig.from_environment(provider=provider or base.provider,
            model_name=model_name or base.model_name,base_url=base_url or (
                base.base_url if not provider or provider==base.provider else None),
            api_key_env=api_key_env,temperature=0)
    else:
        config=replace(base,model_name=model_name or base.model_name)
    return replace(config,max_tokens=2048 if role=='advisor' else 1536,
        thinking_enabled=False,temperature=0,request_attempts=1,parse_attempts=1,
        timeout_seconds=45 if role=='advisor' else 30,
        max_wall_time_seconds=60 if role=='advisor' else 45)
