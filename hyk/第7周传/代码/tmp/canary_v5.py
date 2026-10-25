"""Tiny real wire probe; no benchmark input and no task execution."""
import json
import logging
from pathlib import Path
import subprocess
import sys

def main():
    root = Path('/mnt/lizh639/BestFGS-compare-v5')
    sys.path.insert(0, str(root / 'src'))
    from bestfgs.retrac_adapter import OpenAICompatibleJSONClient, RetracModelConfig
    from bestfgs.raw_baseline import parse_turn
    secret = subprocess.run(['/mnt/lizh639/envs/bestfgs/bin/tmux', 'show-environment', '-g', 'DEEPSEEK_API_KEY'],
                            capture_output=True, text=True, check=True).stdout
    if not secret.startswith('DEEPSEEK_API_KEY='):
        raise RuntimeError('Credential unavailable')
    config = RetracModelConfig(provider='deepseek', model_name='deepseek-flash',
        base_url='https://api.deepseek.com', api_key=secret.strip().split('=', 1)[1],
        temperature=.2, reasoning_effort='high', solve_reasoning_effort='high',
        timeout_seconds=90, max_wall_time_seconds=600, request_attempts=5)
    client = OpenAICompatibleJSONClient(config, diagnostics_path=Path('/mnt/lizh639/notebook-tools/v5-canary-failures.jsonl'))
    payload = client.complete_json(system_prompt='Return exactly one valid JSON object and no other text.',
        user_prompt='For an interface connectivity test only, return {"commands": [], "verification_commands": [], "done": true}.')
    parse_turn(payload, config)
    print(json.dumps({'canary_ok': True, 'task_commands_executed': 0, 'usage': client.usage_summary()}))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        main()
    except Exception as error:
        print(json.dumps({'canary_ok': False, 'error_type': type(error).__name__}))
        sys.exit(2)
