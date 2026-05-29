import pytest

from cloud_incident_rca_agent.domain import (
    CodeEvidenceRequest,
    EvidenceRequestStatus,
    LogEvidenceRequest,
    LogEvidenceRoute,
    SqlEvidenceRequest,
    SqlResultShape,
)
from cloud_incident_rca_agent.orchestrator import EvidenceExecutor


class SucceedingConnector:
    async def execute(self, request):
        from cloud_incident_rca_agent.domain import Evidence, EvidenceSource, ToolResult

        return ToolResult(
            intent_id=request.request_id,
            success=True,
            evidence=[
                Evidence(
                    source=EvidenceSource.OTHER,
                    tool_name="fake",
                    summary="fake evidence",
                    confidence=0.5,
                )
            ],
        )


@pytest.mark.asyncio
async def test_evidence_executor_dispatches_code_request() -> None:
    request = CodeEvidenceRequest(
        hypothesis_ref="checkout code",
        question="Read checkout code",
        expected_signal="handler",
        search_terms=["checkout"],
    )
    executor = EvidenceExecutor(code_inspector=SucceedingConnector())

    result = await executor.execute(request)

    assert result.success is True
    assert result.status == EvidenceRequestStatus.EXECUTED


@pytest.mark.asyncio
async def test_evidence_executor_skips_unconfigured_chrome_route() -> None:
    request = LogEvidenceRequest(
        hypothesis_ref="need console context",
        question="Inspect CLS page",
        expected_signal="project/logstore",
        route=LogEvidenceRoute.CHROME_MCP,
        chrome_page_hint="cls_query",
    )
    result = await EvidenceExecutor().execute(request)

    assert result.success is False
    assert result.status == EvidenceRequestStatus.SKIPPED
    assert "chrome MCP connector is not configured" in result.message


@pytest.mark.asyncio
async def test_evidence_executor_dispatches_sql_request() -> None:
    request = SqlEvidenceRequest(
        hypothesis_ref="orders duplicate",
        question="Check duplicate rows",
        expected_signal="bounded rows",
        schema_context={"orders": ["id", "status"]},
        validation_purpose="Check duplicate rows",
        tables=["orders"],
        sql="select id from orders where id = :id limit 10",
        parameters={"id": "ord_1"},
        expected_result_shape=SqlResultShape.ROWS,
        interpretation_rule="rows > 1 supports duplicate",
        safety_notes="bounded by id",
    )

    result = await EvidenceExecutor().execute(request)

    assert result.success is True
    assert result.status == EvidenceRequestStatus.EXECUTED
