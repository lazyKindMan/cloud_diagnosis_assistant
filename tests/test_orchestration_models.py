import pytest
from pydantic import ValidationError

from cloud_incident_rca_agent.domain import (
    ConnectorError,
    ConnectorErrorCategory,
    Evidence,
    EvidenceSource,
    HumanReviewDecision,
    HumanReviewDecisionStatus,
    HumanReviewRequest,
    InvestigationPlan,
    RiskLevel,
    ToolIntent,
    ToolResult,
    ToolTarget,
)


def test_sensitive_tool_intent_requires_human_review() -> None:
    intent = ToolIntent(
        target=ToolTarget.MYSQL,
        tool_name="query",
        parameters={"sql": "select * from payments"},
        purpose="inspect sensitive payment rows",
        sensitive=True,
    )

    assert intent.requires_human_review is True


def test_investigation_plan_rejects_empty_tool_intents() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        InvestigationPlan(summary="collect initial evidence", tool_intents=[])


def test_connector_error_retryable_defaults_from_category() -> None:
    transient = ConnectorError(
        category=ConnectorErrorCategory.TRANSIENT,
        message="temporary timeout",
    )
    permanent = ConnectorError(
        category=ConnectorErrorCategory.PERMANENT,
        message="unknown connector",
    )

    assert transient.retryable is True
    assert permanent.retryable is False


def test_tool_result_requires_evidence_for_success_and_error_for_failure() -> None:
    with pytest.raises(
        ValidationError,
        match="successful tool results require evidence",
    ):
        ToolResult(intent_id="intent_1", success=True)

    with pytest.raises(
        ValidationError,
        match="failed tool results require connector_error",
    ):
        ToolResult(intent_id="intent_1", success=False)


def test_human_review_decision_requires_modifications_when_approved_with_modifications() -> None:
    with pytest.raises(ValidationError, match="modified_tool_intents"):
        HumanReviewDecision(
            request_id="review_1",
            status=HumanReviewDecisionStatus.APPROVED_WITH_MODIFICATIONS,
        )


def test_human_review_request_stores_affected_intents_and_requires_decision() -> None:
    request = HumanReviewRequest(
        reason="query includes customer identifiers",
        proposed_action="run a restricted log lookup",
        risk_level=RiskLevel.MEDIUM,
        recommended_option="approve restricted lookup",
        affected_tool_intent_ids=["intent_a", "intent_b"],
    )

    assert request.affected_tool_intent_ids == ["intent_a", "intent_b"]
    assert request.requires_decision is True


def test_successful_tool_result_accepts_evidence() -> None:
    evidence = Evidence(
        source=EvidenceSource.CLS_LOG_MCP,
        tool_name="search_logs_by_trace_id",
        summary="trace shows timeout",
        confidence=0.9,
    )

    result = ToolResult(intent_id="intent_1", success=True, evidence=[evidence])

    assert result.evidence == [evidence]
