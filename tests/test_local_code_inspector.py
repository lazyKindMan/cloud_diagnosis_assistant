from pathlib import Path

import pytest

from cloud_incident_rca_agent.connectors import LocalCodeInspector
from cloud_incident_rca_agent.domain import CodeEvidenceRequest


def write_fixture(root: Path) -> None:
    app = root / "app"
    app.mkdir()
    (app / "checkout.py").write_text(
        "def checkout(order_id):\n"
        "    return insert_order(order_id)\n",
        encoding="utf-8",
    )
    (app / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_local_code_inspector_searches_and_reads_snippets(tmp_path) -> None:
    write_fixture(tmp_path)
    request = CodeEvidenceRequest(
        hypothesis_ref="checkout write path",
        question="Find checkout handler",
        expected_signal="checkout calls insert_order",
        search_terms=["checkout", "insert_order"],
        path_allowlist=["app"],
        file_globs=["*.py"],
        max_files=2,
        max_bytes_per_file=1000,
    )

    result = await LocalCodeInspector(tmp_path).execute(request)

    assert result.success is True
    data = result.evidence[0].structured_data
    assert data["matches"][0]["path"] == "app/checkout.py"
    assert "insert_order" in data["matches"][0]["snippet"]


@pytest.mark.asyncio
async def test_local_code_inspector_excludes_secret_files(tmp_path) -> None:
    write_fixture(tmp_path)
    request = CodeEvidenceRequest(
        hypothesis_ref="secret scan",
        question="Do not read secrets",
        expected_signal="secret files are excluded",
        search_terms=["OPENAI_API_KEY"],
        path_allowlist=["app"],
        file_globs=["*"],
        max_files=5,
    )

    result = await LocalCodeInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "no matching code snippets found" in result.connector_error.message


@pytest.mark.asyncio
async def test_local_code_inspector_blocks_path_outside_workspace(tmp_path) -> None:
    request = CodeEvidenceRequest(
        hypothesis_ref="bad path",
        question="Reject parent traversal",
        expected_signal="policy block",
        search_terms=["checkout"],
        path_allowlist=["../"],
    )

    result = await LocalCodeInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "path outside workspace" in result.connector_error.message
