import pytest

from cloud_incident_rca_agent.domain import AgentSession, EvidenceRequestKind
from cloud_incident_rca_agent.llm import FakeLLMClient
from cloud_incident_rca_agent.orchestrator import ContextBuilder, EvidencePlanner


@pytest.mark.asyncio
async def test_fake_llm_creates_evidence_plan_from_context_packet() -> None:
    session = AgentSession(raw_incident="checkout API returns 500")
    packet = ContextBuilder().build(session)

    plan = await FakeLLMClient().create_evidence_plan(packet)

    assert plan.round_number == 1
    assert plan.requests[0].kind == EvidenceRequestKind.CODE
    assert plan.requests[0].question


@pytest.mark.asyncio
async def test_evidence_planner_delegates_to_llm_with_context() -> None:
    planner = EvidencePlanner(FakeLLMClient(), ContextBuilder())
    session = AgentSession(raw_incident="checkout API returns 500")

    plan = await planner.create_plan(session)

    assert plan.objective == "Collect bounded code, log, or SQL evidence for the incident."
