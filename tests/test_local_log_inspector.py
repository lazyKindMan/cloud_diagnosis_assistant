from pathlib import Path

import pytest

from cloud_incident_rca_agent.connectors import LocalLogInspector
from cloud_incident_rca_agent.domain import LogEvidenceRequest, LogEvidenceRoute


@pytest.mark.asyncio
async def test_local_log_inspector_filters_keywords_and_trace(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "checkout.log").write_text(
        "2026-05-29 trace-123 checkout HTTP 500 duplicate key\n"
        "2026-05-29 trace-456 checkout HTTP 200 ok\n",
        encoding="utf-8",
    )
    request = LogEvidenceRequest(
        hypothesis_ref="checkout persistence failure",
        question="Find checkout 500 logs",
        expected_signal="500 duplicate key line",
        route=LogEvidenceRoute.LOCAL_FILE,
        keywords=["500", "duplicate key"],
        trace_id="trace-123",
        local_path_hint="logs/checkout.log",
    )

    result = await LocalLogInspector(tmp_path).execute(request)

    assert result.success is True
    data = result.evidence[0].structured_data
    assert data["matches"] == ["2026-05-29 trace-123 checkout HTTP 500 duplicate key"]


@pytest.mark.asyncio
async def test_local_log_inspector_rejects_missing_path_hint(tmp_path: Path) -> None:
    request = LogEvidenceRequest(
        hypothesis_ref="checkout logs",
        question="Find logs",
        expected_signal="500 lines",
        route=LogEvidenceRoute.LOCAL_FILE,
        keywords=["500"],
    )

    result = await LocalLogInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "local_path_hint is required" in result.connector_error.message


@pytest.mark.asyncio
async def test_local_log_inspector_rejects_secret_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    request = LogEvidenceRequest(
        hypothesis_ref="bad path",
        question="Reject secret path",
        expected_signal="policy block",
        route=LogEvidenceRoute.LOCAL_FILE,
        keywords=["TOKEN"],
        local_path_hint=".env",
    )

    result = await LocalLogInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "local log path is not allowed" in result.connector_error.message
