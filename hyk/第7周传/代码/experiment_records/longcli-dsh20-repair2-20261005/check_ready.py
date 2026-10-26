"""Keyless, quick check; never rewrite an accepted or running configuration."""
import json
from runner import validate_ready

validate_ready()
print(json.dumps({'state': 'ready_not_started', 'tasks': 20, 'context_tokens': 1000000,
                  'output_tokens_per_call': 32768, 'paid_api_requests': 0}))
