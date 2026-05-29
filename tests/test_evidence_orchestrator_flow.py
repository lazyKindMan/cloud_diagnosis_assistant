import pytest

from cloud_incident_rca_agent.domain import (
    AgentSession,
    Evidence,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    EvidenceSource,
    ReplanAction,
    ReplanDecision,
    StopReason,
)
from cloud_incident_rca_agent.llm import FakeLLMClient
from cloud_incident_rca_agent.orchestrator import (
    CloudIncidentRCAOrchestrator,
    ContextBuilder,
    EvidenceAcquisitionPolicy,
    EvidencePlanner,
)


class OneEvidenceExecutor:
    async def execute(self, request):
        return EvidenceRequestResult(
            request_id=request.request_id,
            success=True,
            status=EvidenceRequestStatus.EXECUTED,
            message="executed",
            evidence=[
                Evidence(
                    source=EvidenceSource.OTHER,
                    tool_name="test_evidence",
                    summary="checkout handler calls insert_order",
                    confidence=0.8,
                )
            ],
        )


class ForceSummarizePolicy(EvidenceAcquisitionPolicy):
    def decide_after_round(self, *, session, request_results, top_confidence):
        return ReplanDecision(
            action=ReplanAction.SUMMARIZE,
            reason=StopReason.ROOT_CAUSE_CONFIDENT,
            remaining_rounds=2,
        )


@pytest.mark.asyncio
async def test_orchestrator_records_evidence_round_in_session_memory() -> None:
    session = AgentSession(raw_incident="checkout API returns 500")
    orchestrator = CloudIncidentRCAOrchestrator.with_defaults(
        llm_client=FakeLLMClient(),
        connectors={},
    )
    orchestrator.enable_evidence_planning(
        evidence_planner=EvidencePlanner(FakeLLMClient(), ContextBuilder()),
        evidence_executor=OneEvidenceExecutor(),
        evidence_policy=ForceSummarizePolicy(),
    )

    result = await orchestrator.run_session(session)

    assert result.state.current_state == "DONE"
    assert session.memory.rounds
    assert session.memory.rounds[0].new_evidence_ids
    assert session.memory.attempted_request_fingerprints
    assert result.report is not None
