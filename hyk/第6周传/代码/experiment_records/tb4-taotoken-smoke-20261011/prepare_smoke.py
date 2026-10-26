"""Generate a smoke-only overlay; leave the project's original config intact."""
from pathlib import Path

root = Path(__file__).resolve().parent
source = (root / 'config/kz.patch.yml').read_text()
for before, after in [
    ('__KZ_PLUGIN_PATH__', '/opt/kz/src/plugin.mjs'),
    ('maxRequests: 800', 'maxRequests: 40'),
    ('maxTools: 600', 'maxTools: 80'),
    ('wallSeconds: 7200', 'wallSeconds: 1800'),
    ('maxInputTokens: 1000000', 'maxInputTokens: 128000'),
    ('maxOutputTokens: 32768', 'maxOutputTokens: 8192'),
]:
    assert source.count(before) == 1, before
    source = source.replace(before, after)
(root / '.runtime').mkdir(exist_ok=True)
(root / '.runtime/kz.patch.yml').write_text(source)
