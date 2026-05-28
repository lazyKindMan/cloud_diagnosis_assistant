import pytest

from cloud_incident_rca_agent.domain import Evidence, EvidenceSource, ToolIntent, ToolResult
from cloud_incident_rca_agent.llm import FakeLLMClient
from cloud_incident_rca_agent.orchestrator import CloudIncidentRCAOrchestrator


class FakeConnector:
    async def execute(self, intent: ToolIntent) -> ToolResult:
        return ToolResult(
            intent_id=intent.intent_id,
            success=True,
            evidence=[
                Evidence(
                    source=EvidenceSource.CLS_LOG_MCP,
                    tool_name=intent.tool_name,
                    summary="service returned duplicate key error",
                    confidence=0.8,
                )
            ],
        )


@pytest.mark.asyncio
async def test_orchestrator_fake_backed_happy_path_reaches_done() -> None:
    orchestrator = CloudIncidentRCAOrchestrator.with_defaults(
        llm_client=FakeLLMClient(),
        connectors={"cls-log-mcp": FakeConnector()},
    )

    result = await orchestrator.run("checkout API returns 500")

    assert result.state.current_state == "DONE"
    assert result.report is not None
    assert result.report.most_likely_root_cause == "service returned duplicate key error"
    assert result.state.tool_call_count == 1
