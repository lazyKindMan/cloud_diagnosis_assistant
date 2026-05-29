from cloud_incident_rca_agent.domain import (
    AgentSession,
    CodeEvidenceRequest,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    InvestigationMemory,
    LogEvidenceRequest,
    LogEvidenceRoute,
    ReplanAction,
    RiskLevel,
    SqlEvidenceRequest,
    SqlResultShape,
    StopReason,
)
from cloud_incident_rca_agent.orchestrator import EvidenceAcquisitionPolicy


def test_policy_blocks_duplicate_requests() -> None:
    request = CodeEvidenceRequest(
        hypothesis_ref="checkout handler fails",
        question="Find checkout handler",
        expected_signal="handler path",
        search_terms=["checkout"],
        path_allowlist=["cloud_incident_rca_agent"],
        file_globs=["*.py"],
    )
    policy = EvidenceAcquisitionPolicy()
    fingerprint = policy.fingerprint(request)
    session = AgentSession(
        raw_incident="checkout API returns 500",
        memory=InvestigationMemory(attempted_request_fingerprints=[fingerprint]),
    )

    result = policy.validate_request(session, request)

    assert result is not None
    assert result.status == EvidenceRequestStatus.POLICY_BLOCKED
    assert result.success is False
    assert "duplicate evidence request" in result.message


def test_policy_requires_review_for_high_risk_request() -> None:
    request = LogEvidenceRequest(
        hypothesis_ref="payment data mismatch",
        question="Inspect payment logs",
        expected_signal="payment error",
        risk_level=RiskLevel.HIGH,
        requires_human_review=True,
        route=LogEvidenceRoute.CHROME_MCP,
        chrome_page_hint=None,
    )

    result = EvidenceAcquisitionPolicy().validate_request(
        AgentSession(raw_incident="payment callback mismatch"),
        request,
    )

    assert result is not None
    assert result.status == EvidenceRequestStatus.REQUIRES_REVIEW
    assert result.message == "evidence request requires human review"


def test_policy_decides_replan_when_budget_remains_and_no_new_evidence() -> None:
    session = AgentSession(
        raw_incident="checkout API returns 500",
        round_number=1,
        budgets=InvestigationBudgets(max_plan_rounds=3),
        memory=InvestigationMemory(open_questions=["Need code path"]),
    )

    decision = EvidenceAcquisitionPolicy().decide_after_round(
        session=session,
        request_results=[
            EvidenceRequestResult(
                request_id="request_1",
                success=False,
                status=EvidenceRequestStatus.SKIPPED,
                message="log file not configured",
            )
        ],
        top_confidence=0.2,
    )

    assert decision.action == ReplanAction.REPLAN
    assert decision.reason == StopReason.NO_NEW_EVIDENCE
    assert decision.remaining_rounds == 2


def test_policy_summarizes_when_confidence_is_high() -> None:
    session = AgentSession(raw_incident="checkout API returns 500")

    decision = EvidenceAcquisitionPolicy().decide_after_round(
        session=session,
        request_results=[],
        top_confidence=0.82,
    )

    assert decision.action == ReplanAction.SUMMARIZE
    assert decision.reason == StopReason.ROOT_CAUSE_CONFIDENT


def test_policy_blocks_when_round_budget_exhausted() -> None:
    session = AgentSession(
        raw_incident="checkout API returns 500",
        round_number=3,
        budgets=InvestigationBudgets(max_plan_rounds=3),
    )

    decision = EvidenceAcquisitionPolicy().decide_after_round(
        session=session,
        request_results=[],
        top_confidence=0.1,
    )

    assert decision.action == ReplanAction.BLOCK
    assert decision.reason == StopReason.PLAN_ROUND_BUDGET_EXHAUSTED


def test_sql_fingerprint_normalizes_whitespace() -> None:
    request = SqlEvidenceRequest(
        hypothesis_ref="orders duplicate",
        question="Check duplicate rows",
        expected_signal="duplicate rows",
        schema_context={"orders": ["id"]},
        validation_purpose="Check duplicate order rows",
        tables=["orders"],
        sql="select id from orders where id = :id limit 10",
        parameters={"id": "ord_1"},
        expected_result_shape=SqlResultShape.ROWS,
        interpretation_rule="rows > 1 supports duplicate",
        safety_notes="bounded by id",
    )
    same = request.model_copy(update={"sql": " SELECT   id FROM orders WHERE id = :id LIMIT 10 "})
    policy = EvidenceAcquisitionPolicy()

    assert policy.fingerprint(request) == policy.fingerprint(same)
