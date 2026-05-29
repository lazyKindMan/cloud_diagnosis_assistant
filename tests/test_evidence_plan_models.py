import pytest
from pydantic import ValidationError

from cloud_incident_rca_agent.domain import (
    AgentSession,
    AgentSessionStatus,
    CodeEvidenceRequest,
    ContextPacket,
    EvidenceAcquisitionPlan,
    EvidenceRequestKind,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    InvestigationMemory,
    LogEvidenceRequest,
    LogEvidenceRoute,
    ReplanAction,
    ReplanDecision,
    RiskLevel,
    RoundMemory,
    SqlEvidenceRequest,
    SqlResultShape,
    StopReason,
)


def test_evidence_acquisition_plan_accepts_log_code_and_sql_requests() -> None:
    plan = EvidenceAcquisitionPlan(
        round_number=1,
        objective="Find evidence for checkout API 500s",
        requests=[
            LogEvidenceRequest(
                hypothesis_ref="checkout service throws persistence errors",
                question="Are there checkout 500 logs in the incident window?",
                expected_signal="HTTP 500 log lines with duplicate key errors",
                route=LogEvidenceRoute.LOCAL_FILE,
                service_name="checkout-api",
                time_window="2026-05-29T10:00:00+08:00/2026-05-29T10:30:00+08:00",
                keywords=["500", "duplicate key"],
                local_path_hint="tests/fixtures/evidence_scenarios/logs/checkout.log",
            ),
            CodeEvidenceRequest(
                hypothesis_ref="checkout writes duplicate order rows",
                question="Which code path writes checkout orders?",
                expected_signal="handler calls repository insert",
                search_terms=["checkout", "insert_order"],
                path_allowlist=["cloud_incident_rca_agent"],
                file_globs=["*.py"],
            ),
            SqlEvidenceRequest(
                hypothesis_ref="orders table has conflicting records",
                question="Would a bounded query verify duplicate order rows?",
                expected_signal="safe SQL targets order id and has a limit",
                schema_context={"orders": ["id", "status", "created_at"]},
                validation_purpose="Verify whether one order id has duplicate rows",
                tables=["orders"],
                sql="select id, status from orders where id = :order_id limit 10",
                parameters={"order_id": "ord_123"},
                expected_result_shape=SqlResultShape.ROWS,
                interpretation_rule="More than one row supports duplicate persistence hypothesis",
                safety_notes="Single table, bounded by order id and limit",
            ),
        ],
        max_requests=3,
        stop_conditions=["stop after one supporting signal"],
    )

    assert plan.round_number == 1
    assert [request.kind for request in plan.requests] == [
        EvidenceRequestKind.LOG,
        EvidenceRequestKind.CODE,
        EvidenceRequestKind.SQL,
    ]


def test_evidence_acquisition_plan_rejects_empty_requests() -> None:
    with pytest.raises(ValidationError) as exc_info:
        EvidenceAcquisitionPlan(
            round_number=1,
            objective="Find evidence",
            requests=[],
            max_requests=3,
        )

    assert exc_info.value.errors()[0]["loc"] == ("requests",)


def test_evidence_request_result_requires_message_for_skipped_status() -> None:
    result = EvidenceRequestResult(
        request_id="request_1",
        success=False,
        status=EvidenceRequestStatus.SKIPPED,
        message="chrome connector is not configured",
    )

    assert result.evidence == []
    assert result.message == "chrome connector is not configured"


def test_session_memory_models_capture_single_rca_state() -> None:
    memory = InvestigationMemory(
        working_summary="Checkout API returns 500.",
        stable_facts={"service": "checkout-api"},
        open_questions=["Which repository writes orders?"],
        attempted_request_fingerprints=["code:checkout"],
    )
    session = AgentSession(
        raw_incident="checkout API returns 500",
        current_state="PLAN",
        status=AgentSessionStatus.RUNNING,
        round_number=1,
        budgets=InvestigationBudgets(max_plan_rounds=3),
        memory=memory,
    )

    assert session.raw_incident == "checkout API returns 500"
    assert session.memory.stable_facts["service"] == "checkout-api"
    assert session.checkpoint_version == 1


def test_round_memory_and_context_packet_are_strict() -> None:
    round_memory = RoundMemory(
        round_number=1,
        plan_id="plan_1",
        objective="Find checkout code path",
        request_results=[],
        new_evidence_ids=[],
        hypothesis_summary="No confirmed root cause yet.",
        stop_reason=StopReason.NO_NEW_EVIDENCE,
    )
    packet = ContextPacket(
        incident_summary="Checkout API returns 500.",
        current_hypotheses=["checkout persistence failure: 0.4"],
        recent_evidence_summary=["no log evidence yet"],
        stable_facts={"service": "checkout-api"},
        open_questions=["Need order write path"],
        attempted_requests=["code:checkout"],
        remaining_budgets={"rounds": 2, "tool_calls": 8},
    )

    assert round_memory.stop_reason == StopReason.NO_NEW_EVIDENCE
    assert packet.remaining_budgets["rounds"] == 2
    with pytest.raises(ValidationError):
        ContextPacket(
            incident_summary="Checkout API returns 500.",
            current_hypotheses=[],
            recent_evidence_summary=[],
            stable_facts={},
            open_questions=[],
            attempted_requests=[],
            remaining_budgets={},
            unexpected="value",
        )


def test_replan_decision_records_action_reason_and_budget() -> None:
    decision = ReplanDecision(
        action=ReplanAction.REPLAN,
        reason=StopReason.NO_NEW_EVIDENCE,
        missing_evidence=["Need code path"],
        remaining_rounds=2,
    )

    assert decision.action == ReplanAction.REPLAN
    assert decision.remaining_rounds == 2
