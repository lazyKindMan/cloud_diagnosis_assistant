"""Pydantic models used by the incident investigation state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloud_incident_rca_agent.domain.types import (
    ConfidenceLevel,
    ConnectorErrorCategory,
    EvidenceImplication,
    EvidenceSource,
    HumanReviewDecisionStatus,
    HypothesisStatus,
    InvestigationStatus,
    RiskLevel,
    ToolTarget,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


DEFAULT_REVIEW_REASON = "plan includes actions that require human approval"


class StrictDomainModel(BaseModel):
    """Base model that rejects unknown fields to keep contracts explicit."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class TimeWindow(StrictDomainModel):
    """Optional incident timeframe."""

    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def validate_order(self) -> "TimeWindow":
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("time window start must be before or equal to end")
        return self


class Incident(StrictDomainModel):
    """Normalized description of the incident under investigation."""

    incident_id: str = Field(default_factory=lambda: _new_id("incident"))
    raw_description: str = Field(min_length=1)
    normalized_summary: str | None = None
    service_name: str | None = None
    time_window: TimeWindow | None = None
    environment: str | None = None
    issue_category: str | None = None
    extracted_signals: list[str] = Field(default_factory=list)
    missing_context: list[str] = Field(default_factory=list)


class Evidence(StrictDomainModel):
    """Normalized observation collected from an MCP tool or another source."""

    evidence_id: str = Field(default_factory=lambda: _new_id("evidence"))
    source: EvidenceSource
    tool_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    implication: EvidenceImplication = EvidenceImplication.NEUTRAL
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trace_id: str | None = None
    sensitive: bool = False


class Hypothesis(StrictDomainModel):
    """Candidate explanation for the incident."""

    hypothesis_id: str = Field(default_factory=lambda: _new_id("hypothesis"))
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: HypothesisStatus = HypothesisStatus.CANDIDATE

    @field_validator("supporting_evidence_ids", "contradicting_evidence_ids")
    @classmethod
    def validate_unique_ids(cls, evidence_ids: list[str]) -> list[str]:
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence ids must be unique")
        return evidence_ids


class ExecutionLogEntry(StrictDomainModel):
    """Audit entry for state transitions and later orchestrator actions."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    state: InvestigationStatus
    message: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvestigationState(StrictDomainModel):
    """Mutable investigation state owned by the orchestrator."""

    incident: Incident
    current_state: InvestigationStatus = InvestigationStatus.INTAKE
    tool_call_count: int = Field(default=0, ge=0)
    max_tool_calls: int = Field(default=10, ge=0)
    evidence_list: list[Evidence] = Field(default_factory=list)
    hypothesis_list: list[Hypothesis] = Field(default_factory=list)
    ruled_out_hypotheses: list[Hypothesis] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    execution_log: list[ExecutionLogEntry] = Field(default_factory=list)

    @property
    def tool_budget_remaining(self) -> int:
        return max(self.max_tool_calls - self.tool_call_count, 0)

    @property
    def is_tool_budget_exhausted(self) -> bool:
        return self.tool_call_count >= self.max_tool_calls


class RCAReport(StrictDomainModel):
    """Structured RCA output produced after summarization."""

    incident_summary: str = Field(min_length=1)
    most_likely_root_cause: str = Field(min_length=1)
    confidence_level: ConfidenceLevel
    supporting_evidence: list[str] = Field(default_factory=list)
    ruled_out_alternatives: list[str] = Field(default_factory=list)
    remaining_unknowns: list[str] = Field(default_factory=list)
    recommended_next_actions: list[str] = Field(default_factory=list)


class ToolIntent(StrictDomainModel):
    """Planned connector or browser action proposed by the orchestrator."""

    intent_id: str = Field(default_factory=lambda: _new_id("intent"))
    target: ToolTarget
    tool_name: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    purpose: str = Field(min_length=1)
    sensitive: bool = False
    requires_human_review: bool = False

    @model_validator(mode="after")
    def require_review_for_sensitive_actions(self) -> "ToolIntent":
        if self.sensitive:
            object.__setattr__(self, "requires_human_review", True)
        return self


class ConnectorError(StrictDomainModel):
    """Structured connector failure safe to pass through orchestration state."""

    category: ConnectorErrorCategory
    message: str = Field(min_length=1)
    retryable: bool | None = None
    safe_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def default_retryable_from_category(self) -> "ConnectorError":
        object.__setattr__(
            self,
            "retryable",
            self.category == ConnectorErrorCategory.TRANSIENT,
        )
        return self


class ToolResult(StrictDomainModel):
    """Outcome of executing a planned tool intent."""

    intent_id: str = Field(min_length=1)
    success: bool
    evidence: list[Evidence] = Field(default_factory=list)
    connector_error: ConnectorError | None = None

    @model_validator(mode="after")
    def validate_outcome_payload(self) -> "ToolResult":
        if self.success and not self.evidence:
            raise ValueError("successful tool results require evidence")
        if not self.success and self.connector_error is None:
            raise ValueError("failed tool results require connector_error")
        return self


class InvestigationPlan(StrictDomainModel):
    """Bounded set of tool intents and stopping rules for an investigation."""

    plan_id: str = Field(default_factory=lambda: _new_id("plan"))
    summary: str = Field(min_length=1)
    tool_intents: list[ToolIntent] = Field(min_length=1)
    max_tool_calls: int = Field(default=5, ge=0)
    stopping_criteria: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    review_reason: str | None = None

    @model_validator(mode="after")
    def infer_human_review_requirement(self) -> "InvestigationPlan":
        requires_review = any(intent.requires_human_review for intent in self.tool_intents)
        if requires_review:
            object.__setattr__(self, "requires_human_review", True)
            if self.review_reason is None:
                object.__setattr__(self, "review_reason", DEFAULT_REVIEW_REASON)
        elif self.review_reason == DEFAULT_REVIEW_REASON:
            object.__setattr__(self, "requires_human_review", False)
            object.__setattr__(self, "review_reason", None)
        return self


class HumanReviewRequest(StrictDomainModel):
    """Request for a human decision before performing a risky action."""

    request_id: str = Field(default_factory=lambda: _new_id("review"))
    reason: str = Field(min_length=1)
    proposed_action: str = Field(min_length=1)
    risk_level: RiskLevel
    alternatives: list[str] = Field(default_factory=list)
    recommended_option: str = Field(min_length=1)
    affected_tool_intent_ids: list[str] = Field(default_factory=list)
    requires_decision: bool = True


class HumanReviewDecision(StrictDomainModel):
    """Decision recorded by a reviewer for a human review request."""

    request_id: str = Field(min_length=1)
    status: HumanReviewDecisionStatus
    reviewer_note: str | None = None
    modified_tool_intents: list[ToolIntent] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_modifications_when_modified_approval(self) -> "HumanReviewDecision":
        if (
            self.status == HumanReviewDecisionStatus.APPROVED_WITH_MODIFICATIONS
            and not self.modified_tool_intents
        ):
            raise ValueError(
                "modified_tool_intents are required for approved_with_modifications"
            )
        return self


class OrchestratorRunResult(StrictDomainModel):
    """Top-level result returned by an orchestrator run."""

    state: InvestigationState
    report: RCAReport | None = None
    pending_review: HumanReviewRequest | None = None
    blocked_reason: str | None = None
