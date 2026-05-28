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
