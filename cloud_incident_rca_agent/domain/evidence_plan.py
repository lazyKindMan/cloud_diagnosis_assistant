"""Evidence acquisition and single-session memory models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloud_incident_rca_agent.domain.models import ConnectorError, Evidence
from cloud_incident_rca_agent.domain.types import (
    AgentSessionStatus,
    CodeReadStrategy,
    EvidenceRequestKind,
    EvidenceRequestStatus,
    InvestigationStatus,
    LogEvidenceRoute,
    ReplanAction,
    RiskLevel,
    SqlResultShape,
    StopReason,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictEvidenceModel(BaseModel):
    """Base model for strict evidence planning contracts."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EvidenceRequestBase(StrictEvidenceModel):
    """Shared fields for evidence acquisition requests."""

    request_id: str = Field(default_factory=lambda: _new_id("request"))
    hypothesis_ref: str = Field(min_length=1)
    question: str = Field(min_length=1)
    expected_signal: str = Field(min_length=1)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_human_review: bool = False


class LogEvidenceRequest(EvidenceRequestBase):
    """Plan for log evidence acquisition."""

    kind: Literal[EvidenceRequestKind.LOG] = EvidenceRequestKind.LOG
    route: LogEvidenceRoute
    service_name: str | None = None
    time_window: str | None = None
    keywords: list[str] = Field(default_factory=list)
    trace_id: str | None = None
    query: str | None = None
    aggregation: str | None = None
    chrome_page_hint: str | None = None
    local_path_hint: str | None = None


class CodeEvidenceRequest(EvidenceRequestBase):
    """Plan for bounded local code inspection."""

    kind: Literal[EvidenceRequestKind.CODE] = EvidenceRequestKind.CODE
    search_terms: list[str] = Field(min_length=1)
    path_allowlist: list[str] = Field(default_factory=lambda: ["."])
    file_globs: list[str] = Field(default_factory=lambda: ["*.py"])
    max_files: int = Field(default=5, ge=1, le=20)
    max_bytes_per_file: int = Field(default=20_000, ge=500, le=100_000)
    read_strategy: CodeReadStrategy = CodeReadStrategy.SEARCH_FIRST
    why_these_files: str | None = None


class SqlEvidenceRequest(EvidenceRequestBase):
    """Plan for a SQL validation query."""

    kind: Literal[EvidenceRequestKind.SQL] = EvidenceRequestKind.SQL
    schema_context: dict[str, list[str]] = Field(default_factory=dict)
    validation_purpose: str = Field(min_length=1)
    tables: list[str] = Field(min_length=1)
    sql: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_result_shape: SqlResultShape
    interpretation_rule: str = Field(min_length=1)
    safety_notes: str = Field(min_length=1)


EvidenceRequest = Annotated[
    LogEvidenceRequest | CodeEvidenceRequest | SqlEvidenceRequest,
    Field(discriminator="kind"),
]


class EvidenceAcquisitionPlan(StrictEvidenceModel):
    """Bounded set of evidence requests for one investigation round."""

    plan_id: str = Field(default_factory=lambda: _new_id("evidence_plan"))
    round_number: int = Field(ge=1)
    objective: str = Field(min_length=1)
    requests: list[EvidenceRequest] = Field(min_length=1)
    max_requests: int = Field(default=3, ge=1)
    stop_conditions: list[str] = Field(default_factory=list)
    replan_reason: str | None = None

    @model_validator(mode="after")
    def max_requests_cannot_exceed_requests(self) -> "EvidenceAcquisitionPlan":
        if self.max_requests > len(self.requests):
            object.__setattr__(self, "max_requests", len(self.requests))
        return self


class EvidenceRequestResult(StrictEvidenceModel):
    """Execution or policy result for one evidence request."""

    request_id: str = Field(min_length=1)
    success: bool
    evidence: list[Evidence] = Field(default_factory=list)
    status: EvidenceRequestStatus
    message: str = Field(min_length=1)
    connector_error: ConnectorError | None = None


class ReplanDecision(StrictEvidenceModel):
    """Policy decision after one evidence round."""

    action: ReplanAction
    reason: StopReason
    missing_evidence: list[str] = Field(default_factory=list)
    remaining_rounds: int = Field(ge=0)


class InvestigationBudgets(StrictEvidenceModel):
    """Budgets for one bounded RCA session."""

    max_plan_rounds: int = Field(default=3, ge=1)
    max_requests_per_round: int = Field(default=3, ge=1)
    max_total_tool_calls: int = Field(default=10, ge=0)
    max_code_files_per_round: int = Field(default=5, ge=1)
    max_code_bytes_per_file: int = Field(default=20_000, ge=500)
    max_sql_statements_per_round: int = Field(default=3, ge=0)
    min_confidence_to_summarize: float = Field(default=0.75, ge=0.0, le=1.0)
    forbid_duplicate_requests: bool = True


class RoundMemory(StrictEvidenceModel):
    """Compact record of one evidence planning round."""

    round_number: int = Field(ge=1)
    plan_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    request_results: list[EvidenceRequestResult] = Field(default_factory=list)
    new_evidence_ids: list[str] = Field(default_factory=list)
    hypothesis_summary: str = Field(min_length=1)
    stop_reason: StopReason


class InvestigationMemory(StrictEvidenceModel):
    """Single-session memory for one RCA investigation."""

    working_summary: str = ""
    stable_facts: dict[str, Any] = Field(default_factory=dict)
    rounds: list[RoundMemory] = Field(default_factory=list)
    attempted_request_fingerprints: list[str] = Field(default_factory=list)
    failed_request_fingerprints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    context_token_budget: int = Field(default=4_000, ge=500)


class ContextPacket(StrictEvidenceModel):
    """Bounded context sent to LLM planning calls."""

    incident_summary: str = Field(min_length=1)
    current_hypotheses: list[str] = Field(default_factory=list)
    recent_evidence_summary: list[str] = Field(default_factory=list)
    stable_facts: dict[str, Any] = Field(default_factory=dict)
    open_questions: list[str] = Field(default_factory=list)
    attempted_requests: list[str] = Field(default_factory=list)
    remaining_budgets: dict[str, Any] = Field(default_factory=dict)


class AgentSession(StrictEvidenceModel):
    """Recoverable session for one RCA investigation."""

    session_id: str = Field(default_factory=lambda: _new_id("session"))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_incident: str = Field(min_length=1)
    current_state: InvestigationStatus = InvestigationStatus.INTAKE
    status: AgentSessionStatus = AgentSessionStatus.RUNNING
    round_number: int = Field(default=1, ge=1)
    budgets: InvestigationBudgets = Field(default_factory=InvestigationBudgets)
    memory: InvestigationMemory = Field(default_factory=InvestigationMemory)
    checkpoint_version: int = Field(default=1, ge=1)

    def mark_checkpointed(self) -> None:
        """Advance checkpoint metadata before persisting a session."""

        self.updated_at = datetime.now(UTC)
        self.checkpoint_version += 1
