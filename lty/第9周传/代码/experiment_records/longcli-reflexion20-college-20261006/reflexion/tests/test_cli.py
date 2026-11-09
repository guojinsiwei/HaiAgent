import json

from reflexion.cli import main


def test_config_is_offline_and_has_trial_budget(capsys):
    assert main(["config"]) == 0
    config = json.loads(capsys.readouterr().out)
    assert config["max_trials"] == 3
    assert config["memory_size"] == 3


def test_doctor_checks_presence_without_printing_key(monkeypatch, capsys):
    monkeypatch.setenv("REFLEXION_TEST_KEY", "secret-value-never-print")
    monkeypatch.setattr("reflexion.cli.importlib.import_module", lambda _: (_ for _ in ()).throw(ImportError("missing")))
    assert main(["doctor", "--model", "test-model", "--api-key-env", "REFLEXION_TEST_KEY"]) == 1
    output = capsys.readouterr().out
    assert "secret-value-never-print" not in output
    result = json.loads(output)
    assert result["api_key_present"]
    assert result["network_contacted"] is False
    assert result["native_adapter_importable"] is False

