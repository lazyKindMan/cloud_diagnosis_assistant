import pytest

from cloud_incident_rca_agent.domain import Evidence, EvidenceSource, Incident
from cloud_incident_rca_agent.llm import FakeLLMClient
from cloud_incident_rca_agent.orchestrator import ReportBuilder


@pytest.mark.asyncio
async def test_report_builder_redacts_sensitive_evidence_summaries() -> None:
    builder = ReportBuilder(FakeLLMClient())
    incident = Incident(
        raw_description="payment callback failed",
        normalized_summary="payment callback failed",
    )
    evidence = [
        Evidence(
            source=EvidenceSource.MYSQL,
            tool_name="query",
            summary="customer email and payment row were returned",
            confidence=0.8,
            sensitive=True,
        ),
        Evidence(
            source=EvidenceSource.CLS_LOG_MCP,
            tool_name="search_logs_by_trace_id",
            summary="service returned duplicate key error",
            confidence=0.8,
        ),
    ]

    report = await builder.build(
        incident=incident,
        hypotheses=[],
        evidence=evidence,
        remaining_unknowns=[],
    )

    assert "customer email" not in report.supporting_evidence
    assert report.supporting_evidence == ["service returned duplicate key error"]
