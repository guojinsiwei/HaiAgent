#!/usr/bin/env python3
"""Turn a task directory into a probe task whose "oracle" solution reports on the sandbox instead of solving it.

    python3 v2/tooling/probe/make_probe_task.py --kind net  --task v2/tasks/<id> --out probes/<id>
    python3 v2/tooling/probe/make_probe_task.py --kind leak --task v2/tasks/<id> --out probes/<id>
    harbor run -p probes -e modal -a oracle [--allow-agent-host <your LLM endpoint host>]

kind=net  : curls code hosts / package indexes / a model endpoint from the AGENT phase (expect http=000 for all
            but the allowed host). Set LLM_ENDPOINT (e.g. https://api.anthropic.com) in the task's [agent.env] or
            leave it unset to skip that URL.
kind=leak : reports git history / hidden test files (expect FIXSHA_OBJ=absent, REFLOG=0, STASH=0, ...).
"""
import argparse, re, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ap = argparse.ArgumentParser(); ap.add_argument("--kind", choices=["net", "leak"], required=True)
ap.add_argument("--task", required=True); ap.add_argument("--out", required=True); a = ap.parse_args()
task, out = Path(a.task), Path(a.out)
shutil.copytree(task, out, dirs_exist_ok=True)
iid = task.name
if a.kind == "net":
    solve = (HERE / "netprobe_solve.sh").read_text()
else:
    fix = re.search(r"-([0-9a-f]{40})", iid).group(1)
    tp = (task / "tests" / "test_patch.patch").read_text().split("\n")
    created = [tp[i + 1][6:] for i, l in enumerate(tp[:-1]) if l.startswith("--- /dev/null") and tp[i + 1].startswith("+++ b/")]
    created += [l[len("rename to "):] for l in tp if l.startswith("rename to ")]
    solve = (HERE / "leakprobe_solve.sh.tmpl").format(instance_id=iid, fix_sha=fix,
             created_files=" ".join(f"'{c}'" for c in created), n_created=len(created))
(out / "solution" / "solve.sh").write_text(solve); (out / "solution" / "solve.sh").chmod(0o755)
print(f"probe task written to {out}")
