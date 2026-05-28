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
    Incident,
    InvestigationPlan,
    InvestigationState,
    OrchestratorRunResult,
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
    with pytest.raises(ValidationError) as exc_info:
        InvestigationPlan(summary="collect initial evidence", tool_intents=[])

    error = exc_info.value.errors()[0]
    assert error["loc"] == ("tool_intents",)
    assert error["type"] == "too_short"


def test_investigation_plan_infers_review_requirement_and_reason() -> None:
    intent = ToolIntent(
        target=ToolTarget.MYSQL,
        tool_name="query",
        purpose="inspect potentially sensitive customer records",
        sensitive=True,
    )

    plan = InvestigationPlan(
        summary="collect customer impact evidence",
        tool_intents=[intent],
    )

    assert plan.requires_human_review is True
    assert plan.review_reason == "plan includes actions that require human approval"


def test_investigation_plan_clears_auto_review_when_intents_change() -> None:
    sensitive_intent = ToolIntent(
        target=ToolTarget.MYSQL,
        tool_name="query",
        purpose="inspect sensitive rows",
        sensitive=True,
    )
    safe_intent = ToolIntent(
        target=ToolTarget.CLS_LOG_MCP,
        tool_name="search_logs_by_trace_id",
        purpose="inspect logs",
    )
    plan = InvestigationPlan(summary="collect evidence", tool_intents=[sensitive_intent])
    assert plan.requires_human_review is True

    plan.tool_intents = [safe_intent]

    assert plan.requires_human_review is False
    assert plan.review_reason is None


def test_investigation_plan_preserves_custom_review_reason_without_sensitive_intents() -> None:
    safe_intent = ToolIntent(
        target=ToolTarget.CLS_LOG_MCP,
        tool_name="search_logs_by_trace_id",
        purpose="inspect logs",
    )
    plan = InvestigationPlan(
        summary="collect evidence",
        tool_intents=[safe_intent],
        requires_human_review=True,
        review_reason="operator must choose path",
    )

    assert plan.requires_human_review is True
    assert plan.review_reason == "operator must choose path"


def test_tool_intent_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ToolIntent(
            target=ToolTarget.CLS_LOG_MCP,
            tool_name="search_logs_by_trace_id",
            purpose="inspect trace logs",
            unexpected="value",
        )


def test_connector_error_retryable_defaults_from_category() -> None:
    transient = ConnectorError(
        category=ConnectorErrorCategory.TRANSIENT,
        message="temporary timeout",
    )
    permanent = ConnectorError(
        category=ConnectorErrorCategory.PERMANENT,
        message="unknown connector",
    )
    semantic = ConnectorError(
        category=ConnectorErrorCategory.SEMANTIC,
        message="invalid trace id",
    )
    policy = ConnectorError(
        category=ConnectorErrorCategory.POLICY,
        message="human approval required",
    )

    assert transient.retryable is True
    assert permanent.retryable is False
    assert semantic.retryable is False
    assert policy.retryable is False


def test_connector_error_retryable_updates_when_category_changes() -> None:
    error = ConnectorError(
        category=ConnectorErrorCategory.TRANSIENT,
        message="timeout",
    )
    assert error.retryable is True

    error.category = ConnectorErrorCategory.PERMANENT

    assert error.retryable is False


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


def test_orchestrator_run_result_is_exported_and_accepts_state() -> None:
    state = InvestigationState(
        incident=Incident(raw_description="checkout API returns 500"),
    )

    result = OrchestratorRunResult(state=state)

    assert result.state is state
    assert result.report is None
    assert result.pending_review is None


def test_successful_tool_result_accepts_evidence() -> None:
    evidence = Evidence(
        source=EvidenceSource.CLS_LOG_MCP,
        tool_name="search_logs_by_trace_id",
        summary="trace shows timeout",
        confidence=0.9,
    )

    result = ToolResult(intent_id="intent_1", success=True, evidence=[evidence])

    assert result.evidence == [evidence]
