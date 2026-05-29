from cloud_incident_rca_agent.domain import (
    AgentSession,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    InvestigationMemory,
    RoundMemory,
    StopReason,
)
from cloud_incident_rca_agent.orchestrator import ContextBuilder


def test_context_builder_compacts_session_memory() -> None:
    memory = InvestigationMemory(
        working_summary="Checkout API returns HTTP 500 during order creation.",
        stable_facts={"service": "checkout-api", "route": "/checkout"},
        open_questions=["Which repository writes orders?"],
        attempted_request_fingerprints=["code:checkout"],
        rounds=[
            RoundMemory(
                round_number=1,
                plan_id="plan_1",
                objective="Inspect checkout logs",
                request_results=[
                    EvidenceRequestResult(
                        request_id="request_1",
                        success=False,
                        status=EvidenceRequestStatus.SKIPPED,
                        message="local log path not configured",
                    )
                ],
                new_evidence_ids=[],
                hypothesis_summary="No confirmed root cause.",
                stop_reason=StopReason.NO_NEW_EVIDENCE,
            )
        ],
    )
    session = AgentSession(
        raw_incident="checkout API returns 500",
        memory=memory,
        budgets=InvestigationBudgets(max_plan_rounds=3, max_total_tool_calls=10),
        round_number=2,
    )

    packet = ContextBuilder().build(session)

    assert packet.incident_summary == "Checkout API returns HTTP 500 during order creation."
    assert packet.stable_facts["service"] == "checkout-api"
    assert packet.open_questions == ["Which repository writes orders?"]
    assert packet.attempted_requests == ["code:checkout"]
    assert packet.remaining_budgets["rounds"] == 2
    assert "Round 1: Inspect checkout logs" in packet.recent_evidence_summary[0]


def test_context_builder_falls_back_to_raw_incident() -> None:
    session = AgentSession(raw_incident="payments callback data mismatch")

    packet = ContextBuilder().build(session)

    assert packet.incident_summary == "payments callback data mismatch"
