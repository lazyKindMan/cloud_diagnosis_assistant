import json

from cloud_incident_rca_agent.cli import main


def test_cli_invokes_fake_normalize_and_prints_json(capsys) -> None:
    exit_code = main(
        [
            "llm-invoke",
            "--provider",
            "fake",
            "--task",
            "normalize",
            "checkout API returns 500",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["task"] == "normalize"
    assert output["payload"]["normalized_summary"] == "checkout API returns 500"


def test_cli_fake_provider_override_ignores_invalid_openai_env(monkeypatch, capsys) -> None:
    monkeypatch.setenv("CLOUD_RCA_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "llm-invoke",
            "--provider",
            "fake",
            "--task",
            "normalize",
            "checkout API returns 500",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["task"] == "normalize"
    assert output["payload"]["normalized_summary"] == "checkout API returns 500"


def test_cli_returns_runtime_error_for_provider_setup_failure(monkeypatch, capsys) -> None:
    def fail_build_llm_client(_settings):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("cloud_incident_rca_agent.cli.build_llm_client", fail_build_llm_client)

    exit_code = main(
        [
            "llm-invoke",
            "--provider",
            "fake",
            "--task",
            "normalize",
            "checkout API returns 500",
        ]
    )

    assert exit_code == 1
    assert "provider unavailable" in capsys.readouterr().err


def test_cli_returns_error_for_openai_without_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "llm-invoke",
            "--provider",
            "openai",
            "--task",
            "normalize",
            "checkout API returns 500",
        ]
    )

    assert exit_code == 2
    assert "OPENAI_API_KEY is required" in capsys.readouterr().err
