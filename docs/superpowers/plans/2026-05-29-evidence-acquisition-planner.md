# Evidence Acquisition Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 of the evidence acquisition planner: single-session memory, bounded replanning, log/code/SQL evidence request models, local code and log execution, SQL dry-run validation, and fake-backed orchestrator integration.

**Architecture:** Add a focused evidence planning layer beside the existing orchestrator rather than replacing it. Domain models describe evidence requests and session memory; policy modules enforce budgets and duplicate prevention; local connectors execute bounded code/log/SQL-dry-run requests; the orchestrator uses these components to replan within a fixed session budget.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest, pytest-asyncio, local filesystem JSON session storage, bounded `pathlib`-based local file scanning, existing OpenAI/Fake LLM boundary.

---

## Scope Check

This plan implements the approved design spec's Phase 1 only:

- Include: evidence plan models, single RCA session memory, context compaction, evidence acquisition policy, local code inspector, local log inspector, SQL dry-run validator, evidence executor, fake-backed replanning orchestration, prompt playbooks, and scenario fixtures.
- Exclude from this plan: CLI commands for session control, real Chrome MCP automation, real CLS MCP client configuration, and real MySQL execution.

Those excluded items are Phase 2 and Phase 3 and should get separate implementation plans after Phase 1 is merged.

## File Structure

- Create: `cloud_incident_rca_agent/domain/evidence_plan.py`
  - Evidence request, evidence plan, request result, replan decision, session, memory, and context packet models.
- Modify: `cloud_incident_rca_agent/domain/types.py`
  - Add enums for evidence request kind, routes, request status, stop reasons, replan actions, session status, code read strategy, and SQL result shape.
- Modify: `cloud_incident_rca_agent/domain/__init__.py`
  - Export new models and enums.
- Create: `cloud_incident_rca_agent/orchestrator/evidence_policy.py`
  - Budget checks, duplicate request fingerprints, SQL/log/code request review rules, and replan decisions.
- Create: `cloud_incident_rca_agent/orchestrator/context_builder.py`
  - Compact session memory into `ContextPacket` for LLM calls.
- Create: `cloud_incident_rca_agent/orchestrator/evidence_planner.py`
  - LLM-facing evidence plan creator and deterministic fake-friendly wrapper.
- Create: `cloud_incident_rca_agent/orchestrator/evidence_executor.py`
  - Dispatch `LogEvidenceRequest`, `CodeEvidenceRequest`, and `SqlEvidenceRequest` to local or MCP-backed routes.
- Modify: `cloud_incident_rca_agent/orchestrator/__init__.py`
  - Export new orchestration components.
- Create: `cloud_incident_rca_agent/runtime/session.py`
  - Local JSON-backed `AgentSessionManager`.
- Modify: `cloud_incident_rca_agent/runtime/__init__.py`
  - Export session manager.
- Create: `cloud_incident_rca_agent/connectors/local_code.py`
  - Workspace-bounded code search and snippet reader.
- Create: `cloud_incident_rca_agent/connectors/local_logs.py`
  - Workspace-bounded local log filtering.
- Create: `cloud_incident_rca_agent/connectors/sql_dry_run.py`
  - Strict SQL safety validator and dry-run evidence producer.
- Modify: `cloud_incident_rca_agent/connectors/__init__.py`
  - Export new local connectors.
- Modify: `cloud_incident_rca_agent/llm/client.py`
  - Add evidence-plan method to protocol, fake implementation, and OpenAI implementation.
- Create: `cloud_incident_rca_agent/prompts/evidence_planning.md`
- Create: `cloud_incident_rca_agent/prompts/log_acquisition.md`
- Create: `cloud_incident_rca_agent/prompts/code_inspection.md`
- Create: `cloud_incident_rca_agent/prompts/sql_validation.md`
- Create: `cloud_incident_rca_agent/prompts/replanning.md`
- Test: `tests/test_evidence_plan_models.py`
- Test: `tests/test_session_memory.py`
- Test: `tests/test_context_builder.py`
- Test: `tests/test_evidence_policy.py`
- Test: `tests/test_sql_dry_run.py`
- Test: `tests/test_local_code_inspector.py`
- Test: `tests/test_local_log_inspector.py`
- Test: `tests/test_evidence_executor.py`
- Test: `tests/test_evidence_planner.py`
- Test: `tests/test_evidence_orchestrator_flow.py`
- Test fixtures: `tests/fixtures/evidence_scenarios/`

---

### Task 1: Add Evidence Plan Domain Models

**Files:**
- Create: `cloud_incident_rca_agent/domain/evidence_plan.py`
- Modify: `cloud_incident_rca_agent/domain/types.py`
- Modify: `cloud_incident_rca_agent/domain/__init__.py`
- Test: `tests/test_evidence_plan_models.py`

- [ ] **Step 1: Write failing evidence plan model tests**

Create `tests/test_evidence_plan_models.py`:

```python
import pytest
from pydantic import ValidationError

from cloud_incident_rca_agent.domain import (
    AgentSession,
    AgentSessionStatus,
    CodeEvidenceRequest,
    CodeReadStrategy,
    ContextPacket,
    EvidenceAcquisitionPlan,
    EvidenceRequestKind,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    InvestigationMemory,
    LogEvidenceRequest,
    LogEvidenceRoute,
    ReplanAction,
    ReplanDecision,
    RiskLevel,
    RoundMemory,
    SqlEvidenceRequest,
    SqlResultShape,
    StopReason,
)


def test_evidence_acquisition_plan_accepts_log_code_and_sql_requests() -> None:
    plan = EvidenceAcquisitionPlan(
        round_number=1,
        objective="Find evidence for checkout API 500s",
        requests=[
            LogEvidenceRequest(
                hypothesis_ref="checkout service throws persistence errors",
                question="Are there checkout 500 logs in the incident window?",
                expected_signal="HTTP 500 log lines with duplicate key errors",
                route=LogEvidenceRoute.LOCAL_FILE,
                service_name="checkout-api",
                time_window="2026-05-29T10:00:00+08:00/2026-05-29T10:30:00+08:00",
                keywords=["500", "duplicate key"],
                local_path_hint="tests/fixtures/evidence_scenarios/logs/checkout.log",
            ),
            CodeEvidenceRequest(
                hypothesis_ref="checkout writes duplicate order rows",
                question="Which code path writes checkout orders?",
                expected_signal="handler calls repository insert",
                search_terms=["checkout", "insert_order"],
                path_allowlist=["cloud_incident_rca_agent"],
                file_globs=["*.py"],
            ),
            SqlEvidenceRequest(
                hypothesis_ref="orders table has conflicting records",
                question="Would a bounded query verify duplicate order rows?",
                expected_signal="safe SQL targets order id and has a limit",
                schema_context={"orders": ["id", "status", "created_at"]},
                validation_purpose="Verify whether one order id has duplicate rows",
                tables=["orders"],
                sql="select id, status from orders where id = :order_id limit 10",
                parameters={"order_id": "ord_123"},
                expected_result_shape=SqlResultShape.ROWS,
                interpretation_rule="More than one row supports duplicate persistence hypothesis",
                safety_notes="Single table, bounded by order id and limit",
            ),
        ],
        max_requests=3,
        stop_conditions=["stop after one supporting signal"],
    )

    assert plan.round_number == 1
    assert [request.kind for request in plan.requests] == [
        EvidenceRequestKind.LOG,
        EvidenceRequestKind.CODE,
        EvidenceRequestKind.SQL,
    ]


def test_evidence_acquisition_plan_rejects_empty_requests() -> None:
    with pytest.raises(ValidationError) as exc_info:
        EvidenceAcquisitionPlan(
            round_number=1,
            objective="Find evidence",
            requests=[],
            max_requests=3,
        )

    assert exc_info.value.errors()[0]["loc"] == ("requests",)


def test_evidence_request_result_requires_message_for_skipped_status() -> None:
    result = EvidenceRequestResult(
        request_id="request_1",
        success=False,
        status=EvidenceRequestStatus.SKIPPED,
        message="chrome connector is not configured",
    )

    assert result.evidence == []
    assert result.message == "chrome connector is not configured"


def test_session_memory_models_capture_single_rca_state() -> None:
    memory = InvestigationMemory(
        working_summary="Checkout API returns 500.",
        stable_facts={"service": "checkout-api"},
        open_questions=["Which repository writes orders?"],
        attempted_request_fingerprints=["code:checkout"],
    )
    session = AgentSession(
        raw_incident="checkout API returns 500",
        current_state="PLAN",
        status=AgentSessionStatus.RUNNING,
        round_number=1,
        budgets=InvestigationBudgets(max_plan_rounds=3),
        memory=memory,
    )

    assert session.raw_incident == "checkout API returns 500"
    assert session.memory.stable_facts["service"] == "checkout-api"
    assert session.checkpoint_version == 1


def test_round_memory_and_context_packet_are_strict() -> None:
    round_memory = RoundMemory(
        round_number=1,
        plan_id="plan_1",
        objective="Find checkout code path",
        request_results=[],
        new_evidence_ids=[],
        hypothesis_summary="No confirmed root cause yet.",
        stop_reason=StopReason.NO_NEW_EVIDENCE,
    )
    packet = ContextPacket(
        incident_summary="Checkout API returns 500.",
        current_hypotheses=["checkout persistence failure: 0.4"],
        recent_evidence_summary=["no log evidence yet"],
        stable_facts={"service": "checkout-api"},
        open_questions=["Need order write path"],
        attempted_requests=["code:checkout"],
        remaining_budgets={"rounds": 2, "tool_calls": 8},
    )

    assert round_memory.stop_reason == StopReason.NO_NEW_EVIDENCE
    assert packet.remaining_budgets["rounds"] == 2
    with pytest.raises(ValidationError):
        ContextPacket(
            incident_summary="Checkout API returns 500.",
            current_hypotheses=[],
            recent_evidence_summary=[],
            stable_facts={},
            open_questions=[],
            attempted_requests=[],
            remaining_budgets={},
            unexpected="value",
        )


def test_replan_decision_records_action_reason_and_budget() -> None:
    decision = ReplanDecision(
        action=ReplanAction.REPLAN,
        reason=StopReason.NO_NEW_EVIDENCE,
        missing_evidence=["Need code path"],
        remaining_rounds=2,
    )

    assert decision.action == ReplanAction.REPLAN
    assert decision.remaining_rounds == 2
```

- [ ] **Step 2: Run the model tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_plan_models.py -v
```

Expected: fail with `ImportError` for `EvidenceAcquisitionPlan`.

- [ ] **Step 3: Add evidence planning enums**

Modify `cloud_incident_rca_agent/domain/types.py` by appending these enum classes after `HumanReviewDecisionStatus`:

```python
class EvidenceRequestKind(StrEnum):
    """Kinds of evidence acquisition requests."""

    LOG = "log"
    CODE = "code"
    SQL = "sql"


class LogEvidenceRoute(StrEnum):
    """Routes available for acquiring log evidence."""

    CLS_MCP = "cls_mcp"
    CHROME_MCP = "chrome_mcp"
    LOCAL_FILE = "local_file"


class EvidenceRequestStatus(StrEnum):
    """Execution or policy outcome for one evidence request."""

    EXECUTED = "executed"
    SKIPPED = "skipped"
    POLICY_BLOCKED = "policy_blocked"
    REQUIRES_REVIEW = "requires_review"
    FAILED = "failed"


class ReplanAction(StrEnum):
    """Policy action after one evidence round."""

    REPLAN = "replan"
    SUMMARIZE = "summarize"
    BLOCK = "block"
    HUMAN_REVIEW = "human_review"


class StopReason(StrEnum):
    """Structured reason for stopping or continuing an evidence loop."""

    ROOT_CAUSE_CONFIDENT = "root_cause_confident"
    PLAN_ROUND_BUDGET_EXHAUSTED = "plan_round_budget_exhausted"
    TOOL_BUDGET_EXHAUSTED = "tool_budget_exhausted"
    NO_NEW_EVIDENCE = "no_new_evidence"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    POLICY_BLOCKED = "policy_blocked"
    REPEATED_FAILED_REQUESTS = "repeated_failed_requests"


class AgentSessionStatus(StrEnum):
    """Lifecycle status for one RCA investigation session."""

    RUNNING = "running"
    PENDING_REVIEW = "pending_review"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class CodeReadStrategy(StrEnum):
    """Strategy for local code evidence acquisition."""

    SEARCH_FIRST = "search_first"
    DIRECT_PATH = "direct_path"


class SqlResultShape(StrEnum):
    """Expected shape of a SQL validation query result."""

    SINGLE_ROW = "single_row"
    ROWS = "rows"
    COUNT = "count"
    AGGREGATE = "aggregate"
```

- [ ] **Step 4: Create evidence plan domain models**

Create `cloud_incident_rca_agent/domain/evidence_plan.py`:

```python
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
```

- [ ] **Step 5: Export evidence plan models and enums**

Modify `cloud_incident_rca_agent/domain/__init__.py` by adding imports from `evidence_plan.py` and new enums from `types.py`, then add them to `__all__`:

```python
from cloud_incident_rca_agent.domain.evidence_plan import (
    AgentSession,
    CodeEvidenceRequest,
    ContextPacket,
    EvidenceAcquisitionPlan,
    EvidenceRequestResult,
    InvestigationBudgets,
    InvestigationMemory,
    LogEvidenceRequest,
    ReplanDecision,
    RoundMemory,
    SqlEvidenceRequest,
)
```

Add these enum imports from `cloud_incident_rca_agent.domain.types`:

```python
    AgentSessionStatus,
    CodeReadStrategy,
    EvidenceRequestKind,
    EvidenceRequestStatus,
    LogEvidenceRoute,
    ReplanAction,
    SqlResultShape,
    StopReason,
```

Add each imported name to `__all__`.

- [ ] **Step 6: Run evidence plan model tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_plan_models.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit domain models**

Run:

```bash
git add cloud_incident_rca_agent/domain tests/test_evidence_plan_models.py
git commit -m "Add evidence acquisition domain models"
```

---

### Task 2: Add Single-Session Storage And Context Builder

**Files:**
- Create: `cloud_incident_rca_agent/runtime/session.py`
- Modify: `cloud_incident_rca_agent/runtime/__init__.py`
- Create: `cloud_incident_rca_agent/orchestrator/context_builder.py`
- Modify: `cloud_incident_rca_agent/orchestrator/__init__.py`
- Test: `tests/test_session_memory.py`
- Test: `tests/test_context_builder.py`

- [ ] **Step 1: Write failing session manager tests**

Create `tests/test_session_memory.py`:

```python
import pytest

from cloud_incident_rca_agent.domain import AgentSession, AgentSessionStatus
from cloud_incident_rca_agent.runtime import AgentSessionManager


def test_session_manager_creates_checkpoints_and_loads_session(tmp_path) -> None:
    manager = AgentSessionManager(tmp_path)
    session = manager.create("checkout API returns 500")

    session.memory.stable_facts["service"] = "checkout-api"
    manager.checkpoint(session)

    loaded = manager.load(session.session_id)

    assert loaded.session_id == session.session_id
    assert loaded.memory.stable_facts["service"] == "checkout-api"
    assert loaded.checkpoint_version == 2


def test_session_manager_rejects_missing_session(tmp_path) -> None:
    manager = AgentSessionManager(tmp_path)

    with pytest.raises(FileNotFoundError, match="session missing"):
        manager.load("session_missing")


def test_session_manager_can_resume_running_session(tmp_path) -> None:
    manager = AgentSessionManager(tmp_path)
    session = manager.create("orders API times out")
    session.status = AgentSessionStatus.RUNNING
    manager.checkpoint(session)

    resumed = manager.resume(session.session_id)

    assert resumed.status == AgentSessionStatus.RUNNING


def test_session_manager_rejects_finished_resume(tmp_path) -> None:
    manager = AgentSessionManager(tmp_path)
    session = manager.create("orders API times out")
    session.status = AgentSessionStatus.DONE
    manager.checkpoint(session)

    with pytest.raises(ValueError, match="cannot resume session in status done"):
        manager.resume(session.session_id)
```

- [ ] **Step 2: Write failing context builder tests**

Create `tests/test_context_builder.py`:

```python
from cloud_incident_rca_agent.domain import (
    AgentSession,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    InvestigationMemory,
    RoundMemory,
    StopReason,
)
from cloud_incident_rca_agent.orchestrator import ContextBuilder


def test_context_builder_compacts_session_memory() -> None:
    memory = InvestigationMemory(
        working_summary="Checkout API returns HTTP 500 during order creation.",
        stable_facts={"service": "checkout-api", "route": "/checkout"},
        open_questions=["Which repository writes orders?"],
        attempted_request_fingerprints=["code:checkout"],
        rounds=[
            RoundMemory(
                round_number=1,
                plan_id="plan_1",
                objective="Inspect checkout logs",
                request_results=[
                    EvidenceRequestResult(
                        request_id="request_1",
                        success=False,
                        status=EvidenceRequestStatus.SKIPPED,
                        message="local log path not configured",
                    )
                ],
                new_evidence_ids=[],
                hypothesis_summary="No confirmed root cause.",
                stop_reason=StopReason.NO_NEW_EVIDENCE,
            )
        ],
    )
    session = AgentSession(
        raw_incident="checkout API returns 500",
        memory=memory,
        budgets=InvestigationBudgets(max_plan_rounds=3, max_total_tool_calls=10),
        round_number=2,
    )

    packet = ContextBuilder().build(session)

    assert packet.incident_summary == "Checkout API returns HTTP 500 during order creation."
    assert packet.stable_facts["service"] == "checkout-api"
    assert packet.open_questions == ["Which repository writes orders?"]
    assert packet.attempted_requests == ["code:checkout"]
    assert packet.remaining_budgets["rounds"] == 2
    assert "Round 1: Inspect checkout logs" in packet.recent_evidence_summary[0]


def test_context_builder_falls_back_to_raw_incident() -> None:
    session = AgentSession(raw_incident="payments callback data mismatch")

    packet = ContextBuilder().build(session)

    assert packet.incident_summary == "payments callback data mismatch"
```

- [ ] **Step 3: Run session and context tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_session_memory.py tests/test_context_builder.py -v
```

Expected: fail with imports missing for `AgentSessionManager` and `ContextBuilder`.

- [ ] **Step 4: Implement local JSON session manager**

Create `cloud_incident_rca_agent/runtime/session.py`:

```python
"""Local JSON storage for one RCA agent session."""

from __future__ import annotations

from pathlib import Path

from cloud_incident_rca_agent.domain import AgentSession, AgentSessionStatus


RESUMABLE_STATUSES = {
    AgentSessionStatus.RUNNING,
    AgentSessionStatus.PENDING_REVIEW,
}


class AgentSessionManager:
    """Creates, checkpoints, loads, and resumes RCA sessions."""

    def __init__(self, storage_dir: str | Path) -> None:
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, session_id: str) -> Path:
        return self._storage_dir / f"{session_id}.json"

    def create(self, raw_incident: str) -> AgentSession:
        session = AgentSession(raw_incident=raw_incident)
        self._write(session)
        return session

    def checkpoint(self, session: AgentSession) -> AgentSession:
        session.mark_checkpointed()
        self._write(session)
        return session

    def load(self, session_id: str) -> AgentSession:
        path = self._path_for(session_id)
        if not path.exists():
            raise FileNotFoundError(f"session missing: {session_id}")
        return AgentSession.model_validate_json(path.read_text(encoding="utf-8"))

    def resume(self, session_id: str) -> AgentSession:
        session = self.load(session_id)
        if session.status not in RESUMABLE_STATUSES:
            raise ValueError(f"cannot resume session in status {session.status.value}")
        return session

    def _write(self, session: AgentSession) -> None:
        path = self._path_for(session.session_id)
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
```

- [ ] **Step 5: Implement context builder**

Create `cloud_incident_rca_agent/orchestrator/context_builder.py`:

```python
"""Build bounded LLM context from single-session memory."""

from __future__ import annotations

from cloud_incident_rca_agent.domain import AgentSession, ContextPacket


class ContextBuilder:
    """Compacts an RCA session into the context sent to planning LLM calls."""

    def build(self, session: AgentSession) -> ContextPacket:
        memory = session.memory
        incident_summary = memory.working_summary or session.raw_incident
        recent_rounds = memory.rounds[-3:]
        recent_evidence_summary = [
            (
                f"Round {item.round_number}: {item.objective}; "
                f"stop_reason={item.stop_reason.value}; "
                f"new_evidence={len(item.new_evidence_ids)}"
            )
            for item in recent_rounds
        ]
        remaining_rounds = max(session.budgets.max_plan_rounds - session.round_number + 1, 0)
        remaining_budgets = {
            "rounds": remaining_rounds,
            "tool_calls": session.budgets.max_total_tool_calls,
            "code_files": session.budgets.max_code_files_per_round,
            "code_bytes_per_file": session.budgets.max_code_bytes_per_file,
            "sql_statements": session.budgets.max_sql_statements_per_round,
        }
        return ContextPacket(
            incident_summary=incident_summary,
            current_hypotheses=[],
            recent_evidence_summary=recent_evidence_summary,
            stable_facts=memory.stable_facts,
            open_questions=memory.open_questions,
            attempted_requests=memory.attempted_request_fingerprints,
            remaining_budgets=remaining_budgets,
        )
```

- [ ] **Step 6: Export session manager and context builder**

Modify `cloud_incident_rca_agent/runtime/__init__.py`:

```python
from cloud_incident_rca_agent.runtime.session import AgentSessionManager
```

Add `"AgentSessionManager"` to `__all__`.

Modify `cloud_incident_rca_agent/orchestrator/__init__.py`:

```python
from cloud_incident_rca_agent.orchestrator.context_builder import ContextBuilder
```

Add `"ContextBuilder"` to `__all__`.

- [ ] **Step 7: Run session and context tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_session_memory.py tests/test_context_builder.py -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit session and context components**

Run:

```bash
git add cloud_incident_rca_agent/runtime cloud_incident_rca_agent/orchestrator tests/test_session_memory.py tests/test_context_builder.py
git commit -m "Add RCA session memory and context builder"
```

---

### Task 3: Add Evidence Acquisition Policy And Fingerprints

**Files:**
- Create: `cloud_incident_rca_agent/orchestrator/evidence_policy.py`
- Modify: `cloud_incident_rca_agent/orchestrator/__init__.py`
- Test: `tests/test_evidence_policy.py`

- [ ] **Step 1: Write failing evidence policy tests**

Create `tests/test_evidence_policy.py`:

```python
from cloud_incident_rca_agent.domain import (
    AgentSession,
    CodeEvidenceRequest,
    EvidenceAcquisitionPlan,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    InvestigationMemory,
    LogEvidenceRequest,
    LogEvidenceRoute,
    ReplanAction,
    RiskLevel,
    SqlEvidenceRequest,
    SqlResultShape,
    StopReason,
)
from cloud_incident_rca_agent.orchestrator import EvidenceAcquisitionPolicy


def test_policy_blocks_duplicate_requests() -> None:
    request = CodeEvidenceRequest(
        hypothesis_ref="checkout handler fails",
        question="Find checkout handler",
        expected_signal="handler path",
        search_terms=["checkout"],
        path_allowlist=["cloud_incident_rca_agent"],
        file_globs=["*.py"],
    )
    policy = EvidenceAcquisitionPolicy()
    fingerprint = policy.fingerprint(request)
    session = AgentSession(
        raw_incident="checkout API returns 500",
        memory=InvestigationMemory(attempted_request_fingerprints=[fingerprint]),
    )

    result = policy.validate_request(session, request)

    assert result.status == EvidenceRequestStatus.POLICY_BLOCKED
    assert result.success is False
    assert "duplicate evidence request" in result.message


def test_policy_requires_review_for_high_risk_request() -> None:
    request = LogEvidenceRequest(
        hypothesis_ref="payment data mismatch",
        question="Inspect payment logs",
        expected_signal="payment error",
        risk_level=RiskLevel.HIGH,
        requires_human_review=True,
        route=LogEvidenceRoute.CHROME_MCP,
        chrome_page_hint=None,
    )

    result = EvidenceAcquisitionPolicy().validate_request(
        AgentSession(raw_incident="payment callback mismatch"),
        request,
    )

    assert result.status == EvidenceRequestStatus.REQUIRES_REVIEW
    assert result.message == "evidence request requires human review"


def test_policy_decides_replan_when_budget_remains_and_no_new_evidence() -> None:
    session = AgentSession(
        raw_incident="checkout API returns 500",
        round_number=1,
        budgets=InvestigationBudgets(max_plan_rounds=3),
        memory=InvestigationMemory(open_questions=["Need code path"]),
    )

    decision = EvidenceAcquisitionPolicy().decide_after_round(
        session=session,
        request_results=[
            EvidenceRequestResult(
                request_id="request_1",
                success=False,
                status=EvidenceRequestStatus.SKIPPED,
                message="log file not configured",
            )
        ],
        top_confidence=0.2,
    )

    assert decision.action == ReplanAction.REPLAN
    assert decision.reason == StopReason.NO_NEW_EVIDENCE
    assert decision.remaining_rounds == 2


def test_policy_summarizes_when_confidence_is_high() -> None:
    session = AgentSession(raw_incident="checkout API returns 500")

    decision = EvidenceAcquisitionPolicy().decide_after_round(
        session=session,
        request_results=[],
        top_confidence=0.82,
    )

    assert decision.action == ReplanAction.SUMMARIZE
    assert decision.reason == StopReason.ROOT_CAUSE_CONFIDENT


def test_policy_blocks_when_round_budget_exhausted() -> None:
    session = AgentSession(
        raw_incident="checkout API returns 500",
        round_number=3,
        budgets=InvestigationBudgets(max_plan_rounds=3),
    )

    decision = EvidenceAcquisitionPolicy().decide_after_round(
        session=session,
        request_results=[],
        top_confidence=0.1,
    )

    assert decision.action == ReplanAction.BLOCK
    assert decision.reason == StopReason.PLAN_ROUND_BUDGET_EXHAUSTED


def test_sql_fingerprint_normalizes_whitespace() -> None:
    request = SqlEvidenceRequest(
        hypothesis_ref="orders duplicate",
        question="Check duplicate rows",
        expected_signal="duplicate rows",
        schema_context={"orders": ["id"]},
        validation_purpose="Check duplicate order rows",
        tables=["orders"],
        sql="select id from orders where id = :id limit 10",
        parameters={"id": "ord_1"},
        expected_result_shape=SqlResultShape.ROWS,
        interpretation_rule="rows > 1 supports duplicate",
        safety_notes="bounded by id",
    )
    same = request.model_copy(update={"sql": " SELECT   id FROM orders WHERE id = :id LIMIT 10 "})
    policy = EvidenceAcquisitionPolicy()

    assert policy.fingerprint(request) == policy.fingerprint(same)
```

- [ ] **Step 2: Run policy tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_policy.py -v
```

Expected: fail with `ImportError` for `EvidenceAcquisitionPolicy`.

- [ ] **Step 3: Implement evidence acquisition policy**

Create `cloud_incident_rca_agent/orchestrator/evidence_policy.py`:

```python
"""Policy and fingerprinting for evidence acquisition requests."""

from __future__ import annotations

import json
import re
from typing import Any

from cloud_incident_rca_agent.domain import (
    AgentSession,
    CodeEvidenceRequest,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    LogEvidenceRequest,
    ReplanAction,
    ReplanDecision,
    RiskLevel,
    SqlEvidenceRequest,
    StopReason,
)


class EvidenceAcquisitionPolicy:
    """Enforces per-session evidence acquisition budgets and safety rules."""

    def fingerprint(self, request) -> str:
        if isinstance(request, LogEvidenceRequest):
            payload = {
                "kind": request.kind.value,
                "route": request.route.value,
                "service_name": request.service_name,
                "time_window": request.time_window,
                "trace_id": request.trace_id,
                "keywords": sorted(term.lower() for term in request.keywords),
                "query": self._normalize_text(request.query or ""),
                "local_path_hint": request.local_path_hint,
            }
        elif isinstance(request, CodeEvidenceRequest):
            payload = {
                "kind": request.kind.value,
                "search_terms": sorted(term.lower() for term in request.search_terms),
                "path_allowlist": sorted(request.path_allowlist),
                "file_globs": sorted(request.file_globs),
            }
        elif isinstance(request, SqlEvidenceRequest):
            payload = {
                "kind": request.kind.value,
                "sql": self._normalize_sql(request.sql),
                "tables": sorted(table.lower() for table in request.tables),
                "validation_purpose": self._normalize_text(request.validation_purpose),
                "parameters": sorted(request.parameters),
            }
        else:
            payload = request.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def validate_request(self, session: AgentSession, request) -> EvidenceRequestResult | None:
        fingerprint = self.fingerprint(request)
        if (
            session.budgets.forbid_duplicate_requests
            and fingerprint in session.memory.attempted_request_fingerprints
        ):
            return EvidenceRequestResult(
                request_id=request.request_id,
                success=False,
                status=EvidenceRequestStatus.POLICY_BLOCKED,
                message="duplicate evidence request blocked by session memory",
            )
        if request.requires_human_review or request.risk_level == RiskLevel.HIGH:
            return EvidenceRequestResult(
                request_id=request.request_id,
                success=False,
                status=EvidenceRequestStatus.REQUIRES_REVIEW,
                message="evidence request requires human review",
            )
        return None

    def decide_after_round(
        self,
        *,
        session: AgentSession,
        request_results: list[EvidenceRequestResult],
        top_confidence: float,
    ) -> ReplanDecision:
        budgets: InvestigationBudgets = session.budgets
        if top_confidence >= budgets.min_confidence_to_summarize:
            return ReplanDecision(
                action=ReplanAction.SUMMARIZE,
                reason=StopReason.ROOT_CAUSE_CONFIDENT,
                remaining_rounds=max(budgets.max_plan_rounds - session.round_number, 0),
            )
        remaining_rounds = max(budgets.max_plan_rounds - session.round_number, 0)
        if remaining_rounds <= 0:
            return ReplanDecision(
                action=ReplanAction.BLOCK,
                reason=StopReason.PLAN_ROUND_BUDGET_EXHAUSTED,
                missing_evidence=session.memory.open_questions,
                remaining_rounds=0,
            )
        if any(result.status == EvidenceRequestStatus.REQUIRES_REVIEW for result in request_results):
            return ReplanDecision(
                action=ReplanAction.HUMAN_REVIEW,
                reason=StopReason.REQUIRES_HUMAN_REVIEW,
                missing_evidence=session.memory.open_questions,
                remaining_rounds=remaining_rounds,
            )
        if not any(result.success and result.evidence for result in request_results):
            return ReplanDecision(
                action=ReplanAction.REPLAN,
                reason=StopReason.NO_NEW_EVIDENCE,
                missing_evidence=session.memory.open_questions,
                remaining_rounds=remaining_rounds,
            )
        return ReplanDecision(
            action=ReplanAction.REPLAN,
            reason=StopReason.NO_NEW_EVIDENCE,
            missing_evidence=session.memory.open_questions,
            remaining_rounds=remaining_rounds,
        )

    def _normalize_sql(self, sql: str) -> str:
        return re.sub(r"\s+", " ", sql.strip().lower())

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())
```

- [ ] **Step 4: Export policy**

Modify `cloud_incident_rca_agent/orchestrator/__init__.py`:

```python
from cloud_incident_rca_agent.orchestrator.evidence_policy import EvidenceAcquisitionPolicy
```

Add `"EvidenceAcquisitionPolicy"` to `__all__`.

- [ ] **Step 5: Run policy tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_policy.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit policy**

Run:

```bash
git add cloud_incident_rca_agent/orchestrator/evidence_policy.py cloud_incident_rca_agent/orchestrator/__init__.py tests/test_evidence_policy.py
git commit -m "Add evidence acquisition policy"
```

---

### Task 4: Add SQL Dry-Run Validator

**Files:**
- Create: `cloud_incident_rca_agent/connectors/sql_dry_run.py`
- Modify: `cloud_incident_rca_agent/connectors/__init__.py`
- Test: `tests/test_sql_dry_run.py`

- [ ] **Step 1: Write failing SQL dry-run tests**

Create `tests/test_sql_dry_run.py`:

```python
import pytest

from cloud_incident_rca_agent.connectors import SqlDryRunValidator
from cloud_incident_rca_agent.domain import ConnectorErrorCategory, SqlEvidenceRequest, SqlResultShape


def make_request(sql: str) -> SqlEvidenceRequest:
    return SqlEvidenceRequest(
        hypothesis_ref="orders duplicate",
        question="Check duplicate rows",
        expected_signal="bounded rows",
        schema_context={"orders": ["id", "status", "created_at"]},
        validation_purpose="Check duplicate order rows",
        tables=["orders"],
        sql=sql,
        parameters={"id": "ord_1"},
        expected_result_shape=SqlResultShape.ROWS,
        interpretation_rule="More than one row supports duplicate persistence hypothesis",
        safety_notes="Single table, bounded by order id and limit",
    )


@pytest.mark.asyncio
async def test_sql_dry_run_accepts_safe_select() -> None:
    result = await SqlDryRunValidator().execute(make_request(
        "select id, status from orders where id = :id limit 10"
    ))

    assert result.success is True
    assert result.evidence[0].tool_name == "sql_dry_run"
    assert result.evidence[0].structured_data["sql"].startswith("select id")


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("select * from orders where id = :id limit 10", "SELECT * is not allowed"),
        ("select id from orders", "non-aggregate queries require WHERE"),
        ("select id from orders where id = :id", "non-aggregate queries require LIMIT"),
        ("update orders set status = 'paid'", "only SELECT or WITH queries are allowed"),
        ("select id from orders where id = :id; select id from users", "multi-statement SQL is not allowed"),
        ("select password from users where id = :id limit 1", "sensitive field is not allowed"),
    ],
)
@pytest.mark.asyncio
async def test_sql_dry_run_rejects_unsafe_sql(sql: str, reason: str) -> None:
    result = await SqlDryRunValidator().execute(make_request(sql))

    assert result.success is False
    assert result.connector_error is not None
    assert result.connector_error.category == ConnectorErrorCategory.POLICY
    assert reason in result.connector_error.message
```

- [ ] **Step 2: Run SQL tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_sql_dry_run.py -v
```

Expected: fail with `ImportError` for `SqlDryRunValidator`.

- [ ] **Step 3: Implement SQL dry-run validator**

Create `cloud_incident_rca_agent/connectors/sql_dry_run.py`:

```python
"""SQL dry-run safety validator."""

from __future__ import annotations

import re

from cloud_incident_rca_agent.domain import (
    ConnectorError,
    ConnectorErrorCategory,
    Evidence,
    EvidenceSource,
    SqlEvidenceRequest,
    SqlResultShape,
    ToolResult,
)


SENSITIVE_FIELD = re.compile(
    r"\b(password|passwd|token|secret|access_key|private_key|credential)\b",
    re.IGNORECASE,
)
DISALLOWED_SQL = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|replace|grant|revoke|"
    r"begin|commit|rollback|call|exec|execute|set)\b",
    re.IGNORECASE,
)


class SqlDryRunValidator:
    """Validates generated SQL and emits dry-run evidence."""

    async def execute(self, request: SqlEvidenceRequest) -> ToolResult:
        error = self.validate(request.sql, request.expected_result_shape)
        if error is not None:
            return ToolResult(
                intent_id=request.request_id,
                success=False,
                connector_error=ConnectorError(
                    category=ConnectorErrorCategory.POLICY,
                    message=error,
                ),
            )
        evidence = Evidence(
            source=EvidenceSource.MYSQL,
            tool_name="sql_dry_run",
            summary="SQL query is safe and ready for MySQL MCP execution",
            structured_data={
                "sql": request.sql,
                "tables": request.tables,
                "validation_purpose": request.validation_purpose,
                "interpretation_rule": request.interpretation_rule,
                "parameters": request.parameters,
            },
            confidence=0.5,
        )
        return ToolResult(intent_id=request.request_id, success=True, evidence=[evidence])

    def validate(self, sql: str, result_shape: SqlResultShape) -> str | None:
        stripped = sql.strip()
        lowered = stripped.lower()
        if ";" in stripped.rstrip(";"):
            return "multi-statement SQL is not allowed"
        if DISALLOWED_SQL.search(stripped):
            return "only SELECT or WITH queries are allowed"
        if not (lowered.startswith("select ") or lowered.startswith("with ")):
            return "only SELECT or WITH queries are allowed"
        if re.search(r"select\s+\*", lowered):
            return "SELECT * is not allowed"
        if SENSITIVE_FIELD.search(stripped):
            return "sensitive field is not allowed"
        is_aggregate = result_shape in {SqlResultShape.COUNT, SqlResultShape.AGGREGATE}
        if not is_aggregate and not re.search(r"\bwhere\b", lowered):
            return "non-aggregate queries require WHERE"
        if not is_aggregate and not re.search(r"\blimit\b", lowered):
            return "non-aggregate queries require LIMIT"
        return None
```

- [ ] **Step 4: Export SQL dry-run validator**

Modify `cloud_incident_rca_agent/connectors/__init__.py`:

```python
from cloud_incident_rca_agent.connectors.sql_dry_run import SqlDryRunValidator
```

Add `"SqlDryRunValidator"` to `__all__`.

- [ ] **Step 5: Run SQL tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_sql_dry_run.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit SQL dry-run validator**

Run:

```bash
git add cloud_incident_rca_agent/connectors tests/test_sql_dry_run.py
git commit -m "Add SQL dry-run evidence validator"
```

---

### Task 5: Add Local Code Inspector

**Files:**
- Create: `cloud_incident_rca_agent/connectors/local_code.py`
- Modify: `cloud_incident_rca_agent/connectors/__init__.py`
- Test: `tests/test_local_code_inspector.py`
- Create fixture files under: `tests/fixtures/evidence_scenarios/codebase/`

- [ ] **Step 1: Write failing local code inspector tests**

Create `tests/test_local_code_inspector.py`:

```python
from pathlib import Path

import pytest

from cloud_incident_rca_agent.connectors import LocalCodeInspector
from cloud_incident_rca_agent.domain import CodeEvidenceRequest


def write_fixture(root: Path) -> None:
    app = root / "app"
    app.mkdir()
    (app / "checkout.py").write_text(
        "def checkout(order_id):\n"
        "    return insert_order(order_id)\n",
        encoding="utf-8",
    )
    (app / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_local_code_inspector_searches_and_reads_snippets(tmp_path) -> None:
    write_fixture(tmp_path)
    request = CodeEvidenceRequest(
        hypothesis_ref="checkout write path",
        question="Find checkout handler",
        expected_signal="checkout calls insert_order",
        search_terms=["checkout", "insert_order"],
        path_allowlist=["app"],
        file_globs=["*.py"],
        max_files=2,
        max_bytes_per_file=1000,
    )

    result = await LocalCodeInspector(tmp_path).execute(request)

    assert result.success is True
    data = result.evidence[0].structured_data
    assert data["matches"][0]["path"] == "app/checkout.py"
    assert "insert_order" in data["matches"][0]["snippet"]


@pytest.mark.asyncio
async def test_local_code_inspector_excludes_secret_files(tmp_path) -> None:
    write_fixture(tmp_path)
    request = CodeEvidenceRequest(
        hypothesis_ref="secret scan",
        question="Do not read secrets",
        expected_signal="secret files are excluded",
        search_terms=["OPENAI_API_KEY"],
        path_allowlist=["app"],
        file_globs=["*"],
        max_files=5,
    )

    result = await LocalCodeInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "no matching code snippets found" in result.connector_error.message


@pytest.mark.asyncio
async def test_local_code_inspector_blocks_path_outside_workspace(tmp_path) -> None:
    request = CodeEvidenceRequest(
        hypothesis_ref="bad path",
        question="Reject parent traversal",
        expected_signal="policy block",
        search_terms=["checkout"],
        path_allowlist=["../"],
    )

    result = await LocalCodeInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "path outside workspace" in result.connector_error.message
```

- [ ] **Step 2: Run local code tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_local_code_inspector.py -v
```

Expected: fail with `ImportError` for `LocalCodeInspector`.

- [ ] **Step 3: Implement local code inspector**

Create `cloud_incident_rca_agent/connectors/local_code.py`:

```python
"""Bounded local code inspection."""

from __future__ import annotations

from pathlib import Path

from cloud_incident_rca_agent.domain import (
    CodeEvidenceRequest,
    ConnectorError,
    ConnectorErrorCategory,
    Evidence,
    EvidenceSource,
    ToolResult,
)


EXCLUDED_NAMES = {".git", ".venv", "__pycache__", "cloud_diagnosis_assistant.egg-info"}
SECRET_NAMES = {".env", ".env.local", "id_rsa", "id_dsa"}
SECRET_PARTS = ("secret", "credential", "private_key", "access_key")


class LocalCodeInspector:
    """Searches local workspace files and returns bounded snippets."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._root = Path(workspace_root).resolve()

    async def execute(self, request: CodeEvidenceRequest) -> ToolResult:
        paths_or_error = self._allowed_paths(request.path_allowlist)
        if isinstance(paths_or_error, str):
            return self._error(request.request_id, paths_or_error)
        matches = []
        for base in paths_or_error:
            for pattern in request.file_globs:
                for path in base.rglob(pattern):
                    if len(matches) >= request.max_files:
                        break
                    if not self._is_readable_source(path):
                        continue
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    lowered = text.lower()
                    if not any(term.lower() in lowered for term in request.search_terms):
                        continue
                    snippet = text[: request.max_bytes_per_file]
                    matches.append(
                        {
                            "path": path.relative_to(self._root).as_posix(),
                            "snippet": snippet,
                        }
                    )
                if len(matches) >= request.max_files:
                    break
        if not matches:
            return self._error(request.request_id, "no matching code snippets found")
        evidence = Evidence(
            source=EvidenceSource.OTHER,
            tool_name="local_code_inspection",
            summary=f"Found {len(matches)} local code file(s) matching evidence request",
            structured_data={
                "question": request.question,
                "search_terms": request.search_terms,
                "matches": matches,
            },
            confidence=0.6,
        )
        return ToolResult(intent_id=request.request_id, success=True, evidence=[evidence])

    def _allowed_paths(self, allowlist: list[str]) -> list[Path] | str:
        resolved = []
        for item in allowlist:
            path = (self._root / item).resolve()
            if self._root not in [path, *path.parents]:
                return f"path outside workspace: {item}"
            if path.exists():
                resolved.append(path)
        return resolved

    def _is_readable_source(self, path: Path) -> bool:
        parts = set(path.parts)
        if parts & EXCLUDED_NAMES:
            return False
        if path.name in SECRET_NAMES:
            return False
        lowered = path.name.lower()
        return not any(part in lowered for part in SECRET_PARTS)

    def _error(self, request_id: str, message: str) -> ToolResult:
        return ToolResult(
            intent_id=request_id,
            success=False,
            connector_error=ConnectorError(
                category=ConnectorErrorCategory.POLICY,
                message=message,
            ),
        )
```

- [ ] **Step 4: Export local code inspector**

Modify `cloud_incident_rca_agent/connectors/__init__.py`:

```python
from cloud_incident_rca_agent.connectors.local_code import LocalCodeInspector
```

Add `"LocalCodeInspector"` to `__all__`.

- [ ] **Step 5: Run local code tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_local_code_inspector.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit local code inspector**

Run:

```bash
git add cloud_incident_rca_agent/connectors tests/test_local_code_inspector.py
git commit -m "Add bounded local code inspector"
```

---

### Task 6: Add Local Log Inspector

**Files:**
- Create: `cloud_incident_rca_agent/connectors/local_logs.py`
- Modify: `cloud_incident_rca_agent/connectors/__init__.py`
- Test: `tests/test_local_log_inspector.py`

- [ ] **Step 1: Write failing local log inspector tests**

Create `tests/test_local_log_inspector.py`:

```python
from pathlib import Path

import pytest

from cloud_incident_rca_agent.connectors import LocalLogInspector
from cloud_incident_rca_agent.domain import LogEvidenceRequest, LogEvidenceRoute


@pytest.mark.asyncio
async def test_local_log_inspector_filters_keywords_and_trace(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "checkout.log").write_text(
        "2026-05-29 trace-123 checkout HTTP 500 duplicate key\n"
        "2026-05-29 trace-456 checkout HTTP 200 ok\n",
        encoding="utf-8",
    )
    request = LogEvidenceRequest(
        hypothesis_ref="checkout persistence failure",
        question="Find checkout 500 logs",
        expected_signal="500 duplicate key line",
        route=LogEvidenceRoute.LOCAL_FILE,
        keywords=["500", "duplicate key"],
        trace_id="trace-123",
        local_path_hint="logs/checkout.log",
    )

    result = await LocalLogInspector(tmp_path).execute(request)

    assert result.success is True
    data = result.evidence[0].structured_data
    assert data["matches"] == ["2026-05-29 trace-123 checkout HTTP 500 duplicate key"]


@pytest.mark.asyncio
async def test_local_log_inspector_rejects_missing_path_hint(tmp_path: Path) -> None:
    request = LogEvidenceRequest(
        hypothesis_ref="checkout logs",
        question="Find logs",
        expected_signal="500 lines",
        route=LogEvidenceRoute.LOCAL_FILE,
        keywords=["500"],
    )

    result = await LocalLogInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "local_path_hint is required" in result.connector_error.message


@pytest.mark.asyncio
async def test_local_log_inspector_rejects_secret_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    request = LogEvidenceRequest(
        hypothesis_ref="bad path",
        question="Reject secret path",
        expected_signal="policy block",
        route=LogEvidenceRoute.LOCAL_FILE,
        keywords=["TOKEN"],
        local_path_hint=".env",
    )

    result = await LocalLogInspector(tmp_path).execute(request)

    assert result.success is False
    assert result.connector_error is not None
    assert "local log path is not allowed" in result.connector_error.message
```

- [ ] **Step 2: Run local log tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_local_log_inspector.py -v
```

Expected: fail with `ImportError` for `LocalLogInspector`.

- [ ] **Step 3: Implement local log inspector**

Create `cloud_incident_rca_agent/connectors/local_logs.py`:

```python
"""Bounded local log file inspection."""

from __future__ import annotations

from pathlib import Path

from cloud_incident_rca_agent.domain import (
    ConnectorError,
    ConnectorErrorCategory,
    Evidence,
    EvidenceSource,
    LogEvidenceRequest,
    ToolResult,
)


class LocalLogInspector:
    """Filters local log files by bounded request constraints."""

    def __init__(self, workspace_root: str | Path, *, max_lines: int = 50) -> None:
        self._root = Path(workspace_root).resolve()
        self._max_lines = max_lines

    async def execute(self, request: LogEvidenceRequest) -> ToolResult:
        if not request.local_path_hint:
            return self._error(request.request_id, "local_path_hint is required")
        path = (self._root / request.local_path_hint).resolve()
        if not self._is_allowed(path):
            return self._error(request.request_id, "local log path is not allowed")
        if not path.exists() or not path.is_file():
            return self._error(request.request_id, f"local log file not found: {request.local_path_hint}")
        matches = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            lowered = line.lower()
            if request.trace_id and request.trace_id not in line:
                continue
            if request.keywords and not all(keyword.lower() in lowered for keyword in request.keywords):
                continue
            matches.append(line)
            if len(matches) >= self._max_lines:
                break
        if not matches:
            return self._error(request.request_id, "no matching log lines found")
        evidence = Evidence(
            source=EvidenceSource.OTHER,
            tool_name="local_log_inspection",
            summary=f"Found {len(matches)} local log line(s) matching evidence request",
            structured_data={
                "path": request.local_path_hint,
                "keywords": request.keywords,
                "trace_id": request.trace_id,
                "matches": matches,
            },
            confidence=0.65,
        )
        return ToolResult(intent_id=request.request_id, success=True, evidence=[evidence])

    def _is_allowed(self, path: Path) -> bool:
        if self._root not in [path, *path.parents]:
            return False
        if path.name.startswith("."):
            return False
        lowered = path.name.lower()
        return not any(part in lowered for part in ("secret", "credential", "token", "key"))

    def _error(self, request_id: str, message: str) -> ToolResult:
        return ToolResult(
            intent_id=request_id,
            success=False,
            connector_error=ConnectorError(
                category=ConnectorErrorCategory.POLICY,
                message=message,
            ),
        )
```

- [ ] **Step 4: Export local log inspector**

Modify `cloud_incident_rca_agent/connectors/__init__.py`:

```python
from cloud_incident_rca_agent.connectors.local_logs import LocalLogInspector
```

Add `"LocalLogInspector"` to `__all__`.

- [ ] **Step 5: Run local log tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_local_log_inspector.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit local log inspector**

Run:

```bash
git add cloud_incident_rca_agent/connectors tests/test_local_log_inspector.py
git commit -m "Add bounded local log inspector"
```

---

### Task 7: Add Evidence Executor

**Files:**
- Create: `cloud_incident_rca_agent/orchestrator/evidence_executor.py`
- Modify: `cloud_incident_rca_agent/orchestrator/__init__.py`
- Test: `tests/test_evidence_executor.py`

- [ ] **Step 1: Write failing evidence executor tests**

Create `tests/test_evidence_executor.py`:

```python
import pytest

from cloud_incident_rca_agent.domain import (
    CodeEvidenceRequest,
    EvidenceRequestStatus,
    LogEvidenceRequest,
    LogEvidenceRoute,
    SqlEvidenceRequest,
    SqlResultShape,
)
from cloud_incident_rca_agent.orchestrator import EvidenceExecutor


class SucceedingConnector:
    async def execute(self, request):
        from cloud_incident_rca_agent.domain import Evidence, EvidenceSource, ToolResult

        return ToolResult(
            intent_id=request.request_id,
            success=True,
            evidence=[
                Evidence(
                    source=EvidenceSource.OTHER,
                    tool_name="fake",
                    summary="fake evidence",
                    confidence=0.5,
                )
            ],
        )


@pytest.mark.asyncio
async def test_evidence_executor_dispatches_code_request() -> None:
    request = CodeEvidenceRequest(
        hypothesis_ref="checkout code",
        question="Read checkout code",
        expected_signal="handler",
        search_terms=["checkout"],
    )
    executor = EvidenceExecutor(code_inspector=SucceedingConnector())

    result = await executor.execute(request)

    assert result.success is True
    assert result.status == EvidenceRequestStatus.EXECUTED


@pytest.mark.asyncio
async def test_evidence_executor_skips_unconfigured_chrome_route() -> None:
    request = LogEvidenceRequest(
        hypothesis_ref="need console context",
        question="Inspect CLS page",
        expected_signal="project/logstore",
        route=LogEvidenceRoute.CHROME_MCP,
        chrome_page_hint="cls_query",
    )
    result = await EvidenceExecutor().execute(request)

    assert result.success is False
    assert result.status == EvidenceRequestStatus.SKIPPED
    assert "chrome MCP connector is not configured" in result.message


@pytest.mark.asyncio
async def test_evidence_executor_dispatches_sql_request() -> None:
    request = SqlEvidenceRequest(
        hypothesis_ref="orders duplicate",
        question="Check duplicate rows",
        expected_signal="bounded rows",
        schema_context={"orders": ["id", "status"]},
        validation_purpose="Check duplicate rows",
        tables=["orders"],
        sql="select id from orders where id = :id limit 10",
        parameters={"id": "ord_1"},
        expected_result_shape=SqlResultShape.ROWS,
        interpretation_rule="rows > 1 supports duplicate",
        safety_notes="bounded by id",
    )

    result = await EvidenceExecutor().execute(request)

    assert result.success is True
    assert result.status == EvidenceRequestStatus.EXECUTED
```

- [ ] **Step 2: Run executor tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_executor.py -v
```

Expected: fail with `ImportError` for `EvidenceExecutor`.

- [ ] **Step 3: Implement evidence executor**

Create `cloud_incident_rca_agent/orchestrator/evidence_executor.py`:

```python
"""Dispatch evidence requests to configured execution routes."""

from __future__ import annotations

from cloud_incident_rca_agent.connectors import SqlDryRunValidator
from cloud_incident_rca_agent.domain import (
    CodeEvidenceRequest,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    LogEvidenceRequest,
    LogEvidenceRoute,
    SqlEvidenceRequest,
)


class EvidenceExecutor:
    """Executes evidence requests through local or configured connectors."""

    def __init__(
        self,
        *,
        code_inspector=None,
        local_log_inspector=None,
        cls_connector=None,
        chrome_connector=None,
        sql_validator: SqlDryRunValidator | None = None,
    ) -> None:
        self._code_inspector = code_inspector
        self._local_log_inspector = local_log_inspector
        self._cls_connector = cls_connector
        self._chrome_connector = chrome_connector
        self._sql_validator = sql_validator or SqlDryRunValidator()

    async def execute(self, request) -> EvidenceRequestResult:
        if isinstance(request, CodeEvidenceRequest):
            return await self._execute_with("code inspector is not configured", request, self._code_inspector)
        if isinstance(request, SqlEvidenceRequest):
            return self._from_tool_result(await self._sql_validator.execute(request))
        if isinstance(request, LogEvidenceRequest):
            if request.route == LogEvidenceRoute.LOCAL_FILE:
                return await self._execute_with(
                    "local log inspector is not configured",
                    request,
                    self._local_log_inspector,
                )
            if request.route == LogEvidenceRoute.CLS_MCP:
                return await self._execute_with(
                    "cls-log-mcp connector is not configured",
                    request,
                    self._cls_connector,
                )
            return await self._execute_with(
                "chrome MCP connector is not configured",
                request,
                self._chrome_connector,
            )
        return EvidenceRequestResult(
            request_id=request.request_id,
            success=False,
            status=EvidenceRequestStatus.FAILED,
            message="unsupported evidence request type",
        )

    async def _execute_with(self, missing_message: str, request, connector) -> EvidenceRequestResult:
        if connector is None:
            return EvidenceRequestResult(
                request_id=request.request_id,
                success=False,
                status=EvidenceRequestStatus.SKIPPED,
                message=missing_message,
            )
        return self._from_tool_result(await connector.execute(request))

    def _from_tool_result(self, result) -> EvidenceRequestResult:
        return EvidenceRequestResult(
            request_id=result.intent_id,
            success=result.success,
            evidence=result.evidence,
            status=EvidenceRequestStatus.EXECUTED if result.success else EvidenceRequestStatus.FAILED,
            message="evidence request executed" if result.success else result.connector_error.message,
            connector_error=result.connector_error,
        )
```

- [ ] **Step 4: Export evidence executor**

Modify `cloud_incident_rca_agent/orchestrator/__init__.py`:

```python
from cloud_incident_rca_agent.orchestrator.evidence_executor import EvidenceExecutor
```

Add `"EvidenceExecutor"` to `__all__`.

- [ ] **Step 5: Run executor tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_executor.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit executor**

Run:

```bash
git add cloud_incident_rca_agent/orchestrator tests/test_evidence_executor.py
git commit -m "Add evidence request executor"
```

---

### Task 8: Add Evidence Planner LLM Boundary

**Files:**
- Modify: `cloud_incident_rca_agent/llm/client.py`
- Create: `cloud_incident_rca_agent/orchestrator/evidence_planner.py`
- Modify: `cloud_incident_rca_agent/orchestrator/__init__.py`
- Test: `tests/test_evidence_planner.py`

- [ ] **Step 1: Write failing evidence planner tests**

Create `tests/test_evidence_planner.py`:

```python
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
```

- [ ] **Step 2: Run evidence planner tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_planner.py -v
```

Expected: fail because `FakeLLMClient.create_evidence_plan` and `EvidencePlanner` are missing.

- [ ] **Step 3: Extend LLM protocol and fake/OpenAI implementations**

Modify `cloud_incident_rca_agent/llm/client.py`:

Add imports:

```python
from cloud_incident_rca_agent.domain import ContextPacket, EvidenceAcquisitionPlan
```

Add this method to `LLMClient` protocol:

```python
    async def create_evidence_plan(self, context: ContextPacket) -> EvidenceAcquisitionPlan:
        """Return a bounded evidence acquisition plan for the current session context."""
        ...
```

Add this method to `FakeLLMClient`:

```python
    async def create_evidence_plan(self, context: ContextPacket) -> EvidenceAcquisitionPlan:
        from cloud_incident_rca_agent.domain import CodeEvidenceRequest

        return EvidenceAcquisitionPlan(
            round_number=1,
            objective="Collect bounded code, log, or SQL evidence for the incident.",
            requests=[
                CodeEvidenceRequest(
                    hypothesis_ref="initial code path hypothesis",
                    question="Which local code path is most related to the incident?",
                    expected_signal="Relevant handler, service, or repository code",
                    search_terms=[context.incident_summary.split()[0]],
                    path_allowlist=["cloud_incident_rca_agent"],
                    file_globs=["*.py"],
                )
            ],
            max_requests=1,
            stop_conditions=["one bounded evidence request completes"],
        )
```

Add this method to `OpenAILLMClient`:

```python
    async def create_evidence_plan(self, context: ContextPacket) -> EvidenceAcquisitionPlan:
        prompt = (
            "Create a bounded evidence acquisition plan as JSON matching the "
            "EvidenceAcquisitionPlan schema. Do not request broad searches. "
            f"Context: {context.model_dump(mode='json')}"
        )
        return await self.invoke_json(prompt, EvidenceAcquisitionPlan)
```

- [ ] **Step 4: Implement evidence planner wrapper**

Create `cloud_incident_rca_agent/orchestrator/evidence_planner.py`:

```python
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
```

- [ ] **Step 5: Export evidence planner**

Modify `cloud_incident_rca_agent/orchestrator/__init__.py`:

```python
from cloud_incident_rca_agent.orchestrator.evidence_planner import EvidencePlanner
```

Add `"EvidencePlanner"` to `__all__`.

- [ ] **Step 6: Run evidence planner and existing LLM tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_planner.py tests/test_llm_client.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit evidence planner**

Run:

```bash
git add cloud_incident_rca_agent/llm cloud_incident_rca_agent/orchestrator tests/test_evidence_planner.py
git commit -m "Add evidence planner LLM boundary"
```

---

### Task 9: Integrate Fake-Backed Replanning Flow

**Files:**
- Modify: `cloud_incident_rca_agent/orchestrator/orchestrator.py`
- Test: `tests/test_evidence_orchestrator_flow.py`

- [ ] **Step 1: Write failing evidence orchestrator flow tests**

Create `tests/test_evidence_orchestrator_flow.py`:

```python
import pytest

from cloud_incident_rca_agent.domain import (
    AgentSession,
    CodeEvidenceRequest,
    Evidence,
    EvidenceAcquisitionPlan,
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
    EvidenceExecutor,
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
```

- [ ] **Step 2: Run evidence orchestrator flow test to verify it fails**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_orchestrator_flow.py -v
```

Expected: fail because `enable_evidence_planning` and `run_session` are missing.

- [ ] **Step 3: Add optional evidence planning mode to orchestrator**

Modify `cloud_incident_rca_agent/orchestrator/orchestrator.py`.

Add imports:

```python
from cloud_incident_rca_agent.domain import (
    AgentSession,
    Incident,
    ReplanAction,
    RoundMemory,
    StopReason,
)
from cloud_incident_rca_agent.orchestrator.evidence_policy import EvidenceAcquisitionPolicy
```

Add attributes in `__init__`:

```python
        self._evidence_planner = None
        self._evidence_executor = None
        self._evidence_policy: EvidenceAcquisitionPolicy | None = None
```

Add these methods to `CloudIncidentRCAOrchestrator`:

```python
    def enable_evidence_planning(
        self,
        *,
        evidence_planner,
        evidence_executor,
        evidence_policy: EvidenceAcquisitionPolicy,
    ) -> None:
        self._evidence_planner = evidence_planner
        self._evidence_executor = evidence_executor
        self._evidence_policy = evidence_policy

    async def run_session(self, session: AgentSession) -> OrchestratorRunResult:
        state = InvestigationState(incident=Incident(raw_description=session.raw_incident))
        if (
            self._evidence_planner is None
            or self._evidence_executor is None
            or self._evidence_policy is None
        ):
            return await self.run_state(state)

        state.incident = await self._llm_client.normalize_incident(state.incident.raw_description)
        self._state_machine.transition(state, InvestigationStatus.CLASSIFY)
        state.incident = await self._llm_client.classify_incident(state.incident)
        self._state_machine.transition(state, InvestigationStatus.PLAN)

        plan = await self._evidence_planner.create_plan(session)
        self._state_machine.transition(state, InvestigationStatus.COLLECT_EVIDENCE)
        request_results = []
        for request in plan.requests[: plan.max_requests]:
            policy_result = self._evidence_policy.validate_request(session, request)
            if policy_result is not None:
                request_results.append(policy_result)
                continue
                request_results.append(await self._evidence_executor.execute(request))
                session.memory.attempted_request_fingerprints.append(
                    self._evidence_policy.fingerprint(request)
                )

        new_evidence_ids = []
        for request_result in request_results:
            if request_result.success:
                state.evidence_list.extend(request_result.evidence)
                new_evidence_ids.extend(item.evidence_id for item in request_result.evidence)

        session.memory.rounds.append(
            RoundMemory(
                round_number=session.round_number,
                plan_id=plan.plan_id,
                objective=plan.objective,
                request_results=request_results,
                new_evidence_ids=new_evidence_ids,
                hypothesis_summary="Evidence planning round completed.",
                stop_reason=StopReason.NO_NEW_EVIDENCE,
            )
        )
        decision = self._evidence_policy.decide_after_round(
            session=session,
            request_results=request_results,
            top_confidence=max(
                (item.confidence for item in state.hypothesis_list),
                default=0.0,
            ),
        )
        if decision.action == ReplanAction.REPLAN:
            session.round_number += 1
            self._state_machine.transition(state, InvestigationStatus.PLAN)
            return OrchestratorRunResult(state=state)

        self._state_machine.transition(state, InvestigationStatus.UPDATE_HYPOTHESES)
        state.hypothesis_list = await self._hypothesis_manager.update(
            incident=state.incident,
            existing_hypotheses=state.hypothesis_list,
            evidence=state.evidence_list,
        )
        self._state_machine.transition(state, InvestigationStatus.VERIFY)
        if decision.action == ReplanAction.BLOCK:
            self._state_machine.transition(state, InvestigationStatus.BLOCKED)
            return OrchestratorRunResult(state=state, blocked_reason=decision.reason.value)

        self._state_machine.transition(state, InvestigationStatus.SUMMARIZE)
        report = await self._report_builder.build(
            incident=state.incident,
            hypotheses=state.hypothesis_list,
            evidence=state.evidence_list,
            remaining_unknowns=session.memory.open_questions,
        )
        self._state_machine.transition(state, InvestigationStatus.DONE)
        return OrchestratorRunResult(state=state, report=report)
```

- [ ] **Step 4: Run evidence orchestrator test**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_orchestrator_flow.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Run existing orchestrator tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_orchestrator_flow.py tests/test_state_machine.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit orchestrator integration**

Run:

```bash
git add cloud_incident_rca_agent/orchestrator tests/test_evidence_orchestrator_flow.py
git commit -m "Integrate evidence planning session flow"
```

---

### Task 10: Add Prompt Playbooks And Scenario Fixtures

**Files:**
- Create: `cloud_incident_rca_agent/prompts/evidence_planning.md`
- Create: `cloud_incident_rca_agent/prompts/log_acquisition.md`
- Create: `cloud_incident_rca_agent/prompts/code_inspection.md`
- Create: `cloud_incident_rca_agent/prompts/sql_validation.md`
- Create: `cloud_incident_rca_agent/prompts/replanning.md`
- Create: `tests/fixtures/evidence_scenarios/api_500_code.json`
- Create: `tests/fixtures/evidence_scenarios/failed_persistence_sql.json`
- Create: `tests/fixtures/evidence_scenarios/missing_log_context_replan.json`
- Test: `tests/test_evidence_scenarios.py`

- [ ] **Step 1: Write failing prompt and scenario fixture tests**

Create `tests/test_evidence_scenarios.py`:

```python
import json
from pathlib import Path


PROMPTS = [
    "evidence_planning.md",
    "log_acquisition.md",
    "code_inspection.md",
    "sql_validation.md",
    "replanning.md",
]


def test_prompt_playbooks_exist_and_name_safety_rules() -> None:
    root = Path("cloud_incident_rca_agent/prompts")

    for name in PROMPTS:
        text = (root / name).read_text(encoding="utf-8")
        assert "bounded" in text.lower()
        assert "do not" in text.lower()


def test_evidence_scenario_fixtures_cover_three_core_paths() -> None:
    root = Path("tests/fixtures/evidence_scenarios")
    scenarios = [
        json.loads((root / "api_500_code.json").read_text(encoding="utf-8")),
        json.loads((root / "failed_persistence_sql.json").read_text(encoding="utf-8")),
        json.loads((root / "missing_log_context_replan.json").read_text(encoding="utf-8")),
    ]

    assert {item["focus"] for item in scenarios} == {"code", "sql", "replan"}
    assert all(item["incident"] for item in scenarios)
    assert all(item["expected_stop_reason"] for item in scenarios)
```

- [ ] **Step 2: Run prompt and scenario tests to verify they fail**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_scenarios.py -v
```

Expected: fail with missing prompt files.

- [ ] **Step 3: Add prompt playbooks**

Create `cloud_incident_rca_agent/prompts/evidence_planning.md`:

```markdown
# Evidence Planning

Create bounded evidence requests only. Every request must name the hypothesis it
supports or contradicts, the concrete question it answers, the expected signal,
and the budget or safety constraint that limits it.

Do not request broad discovery such as reading an entire repository, scanning all
logs, or generating SQL without schema context.
```

Create `cloud_incident_rca_agent/prompts/log_acquisition.md`:

```markdown
# Log Acquisition

Prefer `cls-log-mcp` when service, time window, trace id, route, error code, or
specific keywords are known. Use Chrome MCP only to inspect read-only console
context such as CLS query pages, alarms, deployments, traces, or metrics.

Do not query logs without a bounded time window and at least one narrowing
condition.
```

Create `cloud_incident_rca_agent/prompts/code_inspection.md`:

```markdown
# Code Inspection

Use bounded local code searches to find handlers, services, repositories,
configuration, middleware, and tests related to the incident. Explain why each
search term and path is relevant.

Do not read hidden files, credential files, build output, dependency caches, or
large unrelated files.
```

Create `cloud_incident_rca_agent/prompts/sql_validation.md`:

```markdown
# SQL Validation

Generate SQL only from known schema context and a specific hypothesis. Queries
must be read-only, single statement, bounded by WHERE and LIMIT for row queries,
and include an interpretation rule.

Do not use SELECT *, mutation statements, transaction statements, stored
procedures, broad scans, or sensitive fields.
```

Create `cloud_incident_rca_agent/prompts/replanning.md`:

```markdown
# Replanning

Replan only when current evidence cannot confirm or reject the leading
hypotheses and budget remains. Target missing evidence directly and avoid
repeating request fingerprints from prior rounds.

Do not continue after max rounds, repeated failed requests, policy blocks, or a
human review requirement.
```

- [ ] **Step 4: Add scenario fixtures**

Create `tests/fixtures/evidence_scenarios/api_500_code.json`:

```json
{
  "focus": "code",
  "incident": "checkout API returns 500 during order creation",
  "expected_requests": ["code"],
  "expected_stop_reason": "root_cause_confident"
}
```

Create `tests/fixtures/evidence_scenarios/failed_persistence_sql.json`:

```json
{
  "focus": "sql",
  "incident": "order write succeeds in API response but record is missing from database",
  "expected_requests": ["code", "sql"],
  "expected_stop_reason": "root_cause_confident"
}
```

Create `tests/fixtures/evidence_scenarios/missing_log_context_replan.json`:

```json
{
  "focus": "replan",
  "incident": "users see intermittent checkout failures without trace id or time window",
  "expected_requests": ["log", "code"],
  "expected_stop_reason": "no_new_evidence"
}
```

- [ ] **Step 5: Run prompt and scenario tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_evidence_scenarios.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit prompt assets and fixtures**

Run:

```bash
git add cloud_incident_rca_agent/prompts tests/fixtures/evidence_scenarios tests/test_evidence_scenarios.py
git commit -m "Add evidence planning playbooks and scenarios"
```

---

### Task 11: Final Verification

**Files:**
- All files touched by Tasks 1-10.

- [ ] **Step 1: Run focused evidence tests**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest \
  tests/test_evidence_plan_models.py \
  tests/test_session_memory.py \
  tests/test_context_builder.py \
  tests/test_evidence_policy.py \
  tests/test_sql_dry_run.py \
  tests/test_local_code_inspector.py \
  tests/test_local_log_inspector.py \
  tests/test_evidence_executor.py \
  tests/test_evidence_planner.py \
  tests/test_evidence_orchestrator_flow.py \
  tests/test_evidence_scenarios.py \
  -v
```

Expected: all focused evidence tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest -v
```

Expected: all default tests pass. Live integration tests remain gated by environment and may be skipped when credentials or live services are not configured.

- [ ] **Step 3: Inspect final working tree**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing untracked or deleted files remain. The implementation files from this plan are committed.

- [ ] **Step 4: Record completion commit if verification required a final fix**

If Step 1 or Step 2 required a small final correction, run:

```bash
git add cloud_incident_rca_agent tests
git commit -m "Stabilize evidence acquisition planner"
```

Expected: commit succeeds only if there are implementation changes after Task 10.

---

## Self-Review

Spec coverage:

- Evidence acquisition plan models are covered by Task 1.
- Single-session memory, checkpointing, resume, and context compaction are covered by Task 2.
- Request fingerprints, duplicate prevention, replan budget, and stop reasons are covered by Task 3.
- SQL generation validation and dry-run evidence are covered by Task 4.
- Local code inspection is covered by Task 5.
- Local log inspection is covered by Task 6.
- Evidence request dispatch is covered by Task 7.
- LLM evidence planning boundary is covered by Task 8.
- Fake-backed replan session flow is covered by Task 9.
- Prompt playbooks and scenario fixtures are covered by Task 10.
- Full verification is covered by Task 11.

Type consistency:

- Request model names match the approved design: `LogEvidenceRequest`, `CodeEvidenceRequest`, `SqlEvidenceRequest`, `EvidenceAcquisitionPlan`, `EvidenceRequestResult`, `ReplanDecision`, `AgentSession`, `InvestigationMemory`, `RoundMemory`, and `ContextPacket`.
- Enum names used in tests match the implementation steps: `EvidenceRequestKind`, `LogEvidenceRoute`, `EvidenceRequestStatus`, `ReplanAction`, `StopReason`, `AgentSessionStatus`, `CodeReadStrategy`, and `SqlResultShape`.
- Existing `ToolResult` is reused by local connectors and converted to `EvidenceRequestResult` by `EvidenceExecutor`.

Execution boundary:

- This plan intentionally implements Phase 1 only. CLI session commands and live MCP configuration require separate plans.
