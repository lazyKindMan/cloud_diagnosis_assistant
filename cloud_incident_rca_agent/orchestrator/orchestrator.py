"""Thin lifecycle orchestrator for cloud incident RCA."""

from __future__ import annotations

from collections.abc import Mapping

from cloud_incident_rca_agent.connectors import MCPConnector
from cloud_incident_rca_agent.domain import (
    ConnectorErrorCategory,
    HumanReviewDecision,
    HumanReviewDecisionStatus,
    HumanReviewRequest,
    Incident,
    InvestigationPlan,
    InvestigationState,
    InvestigationStatus,
    OrchestratorRunResult,
    ToolTarget,
)
from cloud_incident_rca_agent.llm import LLMClient
from cloud_incident_rca_agent.orchestrator.hypothesis_manager import HypothesisManager
from cloud_incident_rca_agent.orchestrator.planner import Planner
from cloud_incident_rca_agent.orchestrator.report_builder import ReportBuilder
from cloud_incident_rca_agent.orchestrator.state_machine import InvestigationStateMachine
from cloud_incident_rca_agent.orchestrator.tool_router import ToolRouter


class CloudIncidentRCAOrchestrator:
    """Runs the bounded incident RCA lifecycle."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        planner: Planner,
        tool_router: ToolRouter,
        hypothesis_manager: HypothesisManager,
        report_builder: ReportBuilder,
        state_machine: InvestigationStateMachine | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._planner = planner
        self._tool_router = tool_router
        self._hypothesis_manager = hypothesis_manager
        self._report_builder = report_builder
        self._state_machine = state_machine or InvestigationStateMachine()
        self._current_plan: InvestigationPlan | None = None
        self._pending_review: HumanReviewRequest | None = None

    @classmethod
    def with_defaults(
        cls,
        *,
        llm_client: LLMClient,
        connectors: Mapping[str, MCPConnector],
    ) -> "CloudIncidentRCAOrchestrator":
        typed_connectors = {
            ToolTarget(target): connector for target, connector in connectors.items()
        }
        planner = Planner(llm_client)
        return cls(
            llm_client=llm_client,
            planner=planner,
            tool_router=ToolRouter(typed_connectors),
            hypothesis_manager=HypothesisManager(llm_client),
            report_builder=ReportBuilder(llm_client),
        )

    async def run(
        self,
        raw_description: str,
        *,
        review_decision: HumanReviewDecision | None = None,
    ) -> OrchestratorRunResult:
        state = InvestigationState(incident=Incident(raw_description=raw_description))
        return await self.run_state(state, review_decision=review_decision)

    async def run_state(
        self,
        state: InvestigationState,
        *,
        review_decision: HumanReviewDecision | None = None,
    ) -> OrchestratorRunResult:
        report = None
        while not self._state_machine.is_terminal(state.current_state):
            if state.current_state == InvestigationStatus.INTAKE:
                state.incident = await self._llm_client.normalize_incident(
                    state.incident.raw_description
                )
                self._state_machine.transition(state, InvestigationStatus.CLASSIFY)
            elif state.current_state == InvestigationStatus.CLASSIFY:
                state.incident = await self._llm_client.classify_incident(state.incident)
                self._state_machine.transition(state, InvestigationStatus.PLAN)
            elif state.current_state == InvestigationStatus.PLAN:
                self._current_plan = await self._planner.create_plan(state.incident)
                if self._current_plan.requires_human_review:
                    self._pending_review = self._planner.build_review_request(self._current_plan)
                    self._state_machine.transition(state, InvestigationStatus.HUMAN_REVIEW)
                    return OrchestratorRunResult(
                        state=state,
                        pending_review=self._pending_review,
                    )
                self._apply_plan_budget(state, self._current_plan)
                self._state_machine.transition(state, InvestigationStatus.COLLECT_EVIDENCE)
            elif state.current_state == InvestigationStatus.HUMAN_REVIEW:
                if review_decision is None:
                    return OrchestratorRunResult(
                        state=state,
                        pending_review=self._pending_review,
                    )
                outcome = self._apply_review_decision(state, review_decision)
                if outcome == "rejected":
                    return OrchestratorRunResult(state=state)
            elif state.current_state == InvestigationStatus.COLLECT_EVIDENCE:
                if self._current_plan is None:
                    self._state_machine.transition(state, InvestigationStatus.BLOCKED)
                    return OrchestratorRunResult(
                        state=state,
                        blocked_reason="missing investigation plan",
                    )
                if state.is_tool_budget_exhausted:
                    self._state_machine.transition(state, InvestigationStatus.BLOCKED)
                    return OrchestratorRunResult(
                        state=state,
                        blocked_reason="tool budget exhausted before evidence collection",
                    )
                for intent in self._current_plan.tool_intents:
                    if state.is_tool_budget_exhausted:
                        break
                    result = await self._tool_router.execute(intent)
                    state.tool_call_count += 1
                    if result.success:
                        state.evidence_list.extend(result.evidence)
                    elif (
                        result.connector_error
                        and result.connector_error.category != ConnectorErrorCategory.TRANSIENT
                    ):
                        self._state_machine.transition(state, InvestigationStatus.BLOCKED)
                        return OrchestratorRunResult(
                            state=state,
                            blocked_reason=result.connector_error.message,
                        )
                self._state_machine.transition(state, InvestigationStatus.UPDATE_HYPOTHESES)
            elif state.current_state == InvestigationStatus.UPDATE_HYPOTHESES:
                state.hypothesis_list = await self._hypothesis_manager.update(
                    incident=state.incident,
                    existing_hypotheses=state.hypothesis_list,
                    evidence=state.evidence_list,
                )
                self._state_machine.transition(state, InvestigationStatus.VERIFY)
            elif state.current_state == InvestigationStatus.VERIFY:
                self._state_machine.transition(state, InvestigationStatus.SUMMARIZE)
            elif state.current_state == InvestigationStatus.SUMMARIZE:
                report = await self._report_builder.build(
                    incident=state.incident,
                    hypotheses=state.hypothesis_list,
                    evidence=state.evidence_list,
                    remaining_unknowns=state.open_questions,
                )
                self._state_machine.transition(state, InvestigationStatus.DONE)
        return OrchestratorRunResult(state=state, report=report)

    def _apply_plan_budget(self, state: InvestigationState, plan: InvestigationPlan) -> None:
        state.max_tool_calls = min(state.max_tool_calls, plan.max_tool_calls)

    def _apply_review_decision(
        self,
        state: InvestigationState,
        decision: HumanReviewDecision,
    ) -> str:
        if decision.status == HumanReviewDecisionStatus.REJECTED:
            self._state_machine.transition(state, InvestigationStatus.PLAN)
            return "rejected"
        if decision.status == HumanReviewDecisionStatus.APPROVED_WITH_MODIFICATIONS:
            if self._current_plan is not None:
                self._current_plan.tool_intents = decision.modified_tool_intents
                self._current_plan.requires_human_review = False
        if self._current_plan is not None:
            self._apply_plan_budget(state, self._current_plan)
        self._state_machine.transition(state, InvestigationStatus.COLLECT_EVIDENCE)
        return "approved"
