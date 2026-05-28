"""Pydantic models used by the incident investigation state machine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloud_incident_rca_agent.domain.types import (
    ConfidenceLevel,
    EvidenceImplication,
    EvidenceSource,
    HypothesisStatus,
    InvestigationStatus,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


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
