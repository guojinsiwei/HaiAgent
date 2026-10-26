"""Load a private namespace for the SHA-pinned official agent without touching OSWorld."""
import importlib.util
from pathlib import Path
import sys
import types

VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "opencua"


def load_official():
    prefix = "_suz_pinned_opencua"
    if prefix + ".agent" in sys.modules:
        return sys.modules[prefix + ".agent"]
    package = types.ModuleType(prefix)
    package.__path__ = [str(VENDOR)]
    sys.modules[prefix] = package
    for name in ("utils", "prompts"):
        spec = importlib.util.spec_from_file_location(prefix + "." + name, VENDOR / (name + ".py"))
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    # Only import paths are rewritten in memory. Vendor files stay byte-identical.
    source = (VENDOR / "opencua_agent.py").read_text(encoding="utf-8")
    source = source.replace("from mm_agents.opencua.utils import", f"from {prefix}.utils import")
    source = source.replace("from mm_agents.opencua.prompts import", f"from {prefix}.prompts import")
    module = types.ModuleType(prefix + ".agent")
    module.__file__ = str(VENDOR / "opencua_agent.py")
    sys.modules[module.__name__] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module
