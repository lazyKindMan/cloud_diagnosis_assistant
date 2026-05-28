"""RCA report builder."""

from __future__ import annotations

from cloud_incident_rca_agent.domain import Evidence, Hypothesis, Incident, RCAReport
from cloud_incident_rca_agent.llm import LLMClient


class ReportBuilder:
    """Builds structured reports while keeping sensitive evidence out of summaries."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def build(
        self,
        *,
        incident: Incident,
        hypotheses: list[Hypothesis],
        evidence: list[Evidence],
        remaining_unknowns: list[str],
    ) -> RCAReport:
        safe_evidence = [item for item in evidence if not item.sensitive]
        return await self._llm_client.build_report(
            incident=incident,
            hypotheses=hypotheses,
            evidence=safe_evidence,
            remaining_unknowns=remaining_unknowns,
        )
