import pytest

from cloud_incident_rca_agent.domain import (
    ConnectorError,
    ConnectorErrorCategory,
    Evidence,
    EvidenceSource,
    HumanReviewDecision,
    HumanReviewDecisionStatus,
    Incident,
    InvestigationPlan,
    ToolIntent,
    ToolResult,
)
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


class ReviewRequiredLLMClient(FakeLLMClient):
    async def create_plan(self, incident: Incident) -> InvestigationPlan:
        plan = await super().create_plan(incident)
        plan.tool_intents[0].sensitive = True
        plan.tool_intents[0].requires_human_review = True
        plan.requires_human_review = True
        plan.review_reason = "log search may include sensitive payment data"
        return plan


@pytest.mark.asyncio
async def test_orchestrator_pauses_at_human_review() -> None:
    orchestrator = CloudIncidentRCAOrchestrator.with_defaults(
        llm_client=ReviewRequiredLLMClient(),
        connectors={"cls-log-mcp": FakeConnector()},
    )

    result = await orchestrator.run("payment callback data mismatch")

    assert result.state.current_state == "HUMAN_REVIEW"
    assert result.pending_review is not None
    assert result.pending_review.reason == "log search may include sensitive payment data"


@pytest.mark.asyncio
async def test_orchestrator_resumes_after_review_approval() -> None:
    orchestrator = CloudIncidentRCAOrchestrator.with_defaults(
        llm_client=ReviewRequiredLLMClient(),
        connectors={"cls-log-mcp": FakeConnector()},
    )
    paused = await orchestrator.run("payment callback data mismatch")

    assert paused.pending_review is not None
    resumed = await orchestrator.run_state(
        paused.state,
        review_decision=HumanReviewDecision(
            request_id=paused.pending_review.request_id,
            status=HumanReviewDecisionStatus.APPROVED,
            reviewer_note="approved read-only log search",
        ),
    )

    assert resumed.state.current_state == "DONE"
    assert resumed.report is not None


@pytest.mark.asyncio
async def test_orchestrator_replans_after_review_rejection() -> None:
    orchestrator = CloudIncidentRCAOrchestrator.with_defaults(
        llm_client=ReviewRequiredLLMClient(),
        connectors={"cls-log-mcp": FakeConnector()},
    )
    paused = await orchestrator.run("payment callback data mismatch")

    assert paused.pending_review is not None
    resumed = await orchestrator.run_state(
        paused.state,
        review_decision=HumanReviewDecision(
            request_id=paused.pending_review.request_id,
            status=HumanReviewDecisionStatus.REJECTED,
            reviewer_note="narrow scope first",
        ),
    )

    assert resumed.state.current_state == "PLAN"
    assert resumed.pending_review is None


class PermanentFailureConnector:
    async def execute(self, intent: ToolIntent) -> ToolResult:
        return ToolResult(
            intent_id=intent.intent_id,
            success=False,
            connector_error=ConnectorError(
                category=ConnectorErrorCategory.PERMANENT,
                message="MCP server unavailable",
            ),
        )


class ZeroBudgetLLMClient(FakeLLMClient):
    async def create_plan(self, incident: Incident) -> InvestigationPlan:
        plan = await super().create_plan(incident)
        plan.max_tool_calls = 0
        return plan


@pytest.mark.asyncio
async def test_orchestrator_blocks_on_permanent_connector_failure() -> None:
    orchestrator = CloudIncidentRCAOrchestrator.with_defaults(
        llm_client=FakeLLMClient(),
        connectors={"cls-log-mcp": PermanentFailureConnector()},
    )

    result = await orchestrator.run("checkout API returns 500")

    assert result.state.current_state == "BLOCKED"
    assert result.blocked_reason == "MCP server unavailable"


@pytest.mark.asyncio
async def test_orchestrator_blocks_when_plan_has_no_tool_budget() -> None:
    orchestrator = CloudIncidentRCAOrchestrator.with_defaults(
        llm_client=ZeroBudgetLLMClient(),
        connectors={"cls-log-mcp": FakeConnector()},
    )

    result = await orchestrator.run("checkout API returns 500")

    assert result.state.current_state == "BLOCKED"
    assert result.blocked_reason == "tool budget exhausted before evidence collection"
