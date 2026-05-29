"""Evidence acquisition planning component."""

from __future__ import annotations

from cloud_incident_rca_agent.domain import AgentSession, EvidenceAcquisitionPlan
from cloud_incident_rca_agent.llm import LLMClient
from cloud_incident_rca_agent.orchestrator.context_builder import ContextBuilder


class EvidencePlanner:
    """Creates bounded evidence acquisition plans from session context."""

    def __init__(self, llm_client: LLMClient, context_builder: ContextBuilder) -> None:
        self._llm_client = llm_client
        self._context_builder = context_builder

    async def create_plan(self, session: AgentSession) -> EvidenceAcquisitionPlan:
        packet = self._context_builder.build(session)
        plan = await self._llm_client.create_evidence_plan(packet)
        plan.round_number = session.round_number
        return plan
