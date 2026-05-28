"""Investigation planning component."""

from __future__ import annotations

from cloud_incident_rca_agent.domain import HumanReviewRequest, InvestigationPlan, RiskLevel
from cloud_incident_rca_agent.llm import LLMClient


class Planner:
    """Creates bounded investigation plans and review requests."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    async def create_plan(self, incident) -> InvestigationPlan:
        return await self._llm_client.create_plan(incident)

    def build_review_request(self, plan: InvestigationPlan) -> HumanReviewRequest:
        affected = [intent.intent_id for intent in plan.tool_intents if intent.requires_human_review]
        return HumanReviewRequest(
            reason=plan.review_reason or "plan requires human approval",
            proposed_action=plan.summary,
            risk_level=RiskLevel.HIGH if affected else RiskLevel.MEDIUM,
            alternatives=["revise the investigation plan", "stop and summarize current findings"],
            recommended_option="approve the bounded read-only investigation plan",
            affected_tool_intent_ids=affected,
        )
