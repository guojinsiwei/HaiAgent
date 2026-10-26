import json
from types import SimpleNamespace
import pytest
from recuris.cli import main
from recuris.memory import load_memory


def test_help_does_not_start_a_campaign(capsys):
    with pytest.raises(SystemExit) as stopped:
        main(["--help"])
    assert stopped.value.code == 0
    assert "tta" in capsys.readouterr().out


def test_config_and_seed_are_offline(tmp_path, capsys):
    assert main(["config"]) == 0
    assert json.loads(capsys.readouterr().out)["max_steps"] == 200
    target = tmp_path / "seed.json"
    assert main(["seed", "--profile", "terminal", "--output", str(target)]) == 0
    memory = load_memory(target)
    assert memory["E"][0]["id"] == "terminal_closed_loop"
    assert memory["rho"]["max_skills"] == 8
    assert main(["seed", "--output", str(target)]) == 2


def test_doctor_no_key_or_network(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    import importlib
    original_import = importlib.import_module
    def missing_adapter(name, *args, **kwargs):
        if name == "recuris.longcli":
            raise ImportError("missing benchmark")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr("recuris.cli.importlib.import_module", missing_adapter)
    assert main(["doctor", "--model", "offline-model"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["network_contacted"] is False
    assert report["adapter_importable"] is False


def test_tta_cli_builds_configuration_without_invoking_real_harness(monkeypatch, tmp_path, capsys):
    seen = []
    def fake(config, meta_agent=None):
        seen.append((config, meta_agent))
        return {"status": "exhausted", "official_success": False}
    monkeypatch.setattr("recuris.tta.run_tta", fake)
    args = ["tta", "--model", "offline", "--mode", "frozen", "--benchmark-root", str(tmp_path),
            "--task-id", "example", "--output-dir", str(tmp_path / "out"), "--agent-kwarg", "max_steps=20"]
    assert main(args) == 0
    assert seen[0][0].agent_kwargs["max_steps"] == 20
    assert seen[0][0].attempts == 4 and seen[0][1] is None
    assert main(args + ["--agent-kwarg", "temperature=0"]) == 2


def test_propose_rejects_success_without_calling_meta(monkeypatch, tmp_path):
    monkeypatch.setattr("recuris.tta.read_attempt", lambda _: {"success": True})
    assert main(["propose", "--attempt-dir", str(tmp_path), "--output-dir", str(tmp_path / "candidate")]) == 2
    assert not (tmp_path / "candidate").exists()


def test_propose_preserves_gate_input_digest(monkeypatch, tmp_path):
    from copy import deepcopy
    from recuris.evolution import Candidate
    from recuris.memory import memory_digest

    base = load_memory()
    proposed = deepcopy(base)
    proposed["E"].append({"id": "example", "description": "Example", "content": "API_KEY=placeholder", "tags": []})
    candidate = Candidate([], memory_digest(base), proposed, ["E"], memory_digest(proposed), "cross_task")
    attempt = {"success": False, "memory": base, "task_id": "example", "instruction": "Public task", "trace": []}
    monkeypatch.setattr("recuris.tta.read_attempt", lambda _: attempt)
    monkeypatch.setattr("recuris.cli._meta", lambda _: SimpleNamespace(propose=lambda *a, **kw: candidate))
    target = tmp_path / "candidate"
    assert main(["propose", "--attempt-dir", str(tmp_path), "--output-dir", str(target)]) == 0
    record = json.loads((target / "candidate.json").read_text(encoding="utf-8"))
    assert record["candidate_memory"] == proposed
    assert record["candidate_digest"] == memory_digest(record["candidate_memory"])
    assert load_memory(target / "memory.json") == proposed
