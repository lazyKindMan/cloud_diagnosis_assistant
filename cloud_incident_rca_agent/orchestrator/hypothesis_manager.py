"""Hypothesis update component."""

from __future__ import annotations

from cloud_incident_rca_agent.domain import Evidence, Hypothesis, Incident
from cloud_incident_rca_agent.llm import LLMClient


class HypothesisManager:
    """Updates candidate hypotheses from accumulated evidence."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def update(
        self,
        *,
        incident: Incident,
        existing_hypotheses: list[Hypothesis],
        evidence: list[Evidence],
    ) -> list[Hypothesis]:
        return await self._llm_client.update_hypotheses(
            incident=incident,
            existing_hypotheses=existing_hypotheses,
            evidence=evidence,
        )
