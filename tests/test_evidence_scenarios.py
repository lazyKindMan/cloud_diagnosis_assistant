import json
from pathlib import Path


PROMPTS = [
    "evidence_planning.md",
    "log_acquisition.md",
    "code_inspection.md",
    "sql_validation.md",
    "replanning.md",
]


def test_prompt_playbooks_exist_and_name_safety_rules() -> None:
    root = Path("cloud_incident_rca_agent/prompts")

    for name in PROMPTS:
        text = (root / name).read_text(encoding="utf-8")
        assert "bounded" in text.lower()
        assert "do not" in text.lower()


def test_evidence_scenario_fixtures_cover_three_core_paths() -> None:
    root = Path("tests/fixtures/evidence_scenarios")
    scenarios = [
        json.loads((root / "api_500_code.json").read_text(encoding="utf-8")),
        json.loads((root / "failed_persistence_sql.json").read_text(encoding="utf-8")),
        json.loads((root / "missing_log_context_replan.json").read_text(encoding="utf-8")),
    ]

    assert {item["focus"] for item in scenarios} == {"code", "sql", "replan"}
    assert all(item["incident"] for item in scenarios)
    assert all(item["expected_stop_reason"] for item in scenarios)
