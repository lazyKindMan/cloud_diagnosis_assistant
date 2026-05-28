from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cloud_incident_rca_agent.domain import (
    Evidence,
    EvidenceSource,
    Hypothesis,
    Incident,
    InvestigationState,
    TimeWindow,
)


def test_incident_state_defaults_are_ready_for_intake() -> None:
    incident = Incident(raw_description="checkout API returns 500")
    state = InvestigationState(incident=incident, max_tool_calls=3)

    assert state.current_state == "INTAKE"
    assert state.tool_budget_remaining == 3
    assert state.evidence_list == []


def test_time_window_rejects_inverted_range() -> None:
    with pytest.raises(ValidationError, match="time window start"):
        TimeWindow(
            start=datetime(2026, 5, 28, 12, tzinfo=UTC),
            end=datetime(2026, 5, 28, 11, tzinfo=UTC),
        )


def test_evidence_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            source=EvidenceSource.CLS_LOG_MCP,
            tool_name="search_logs_by_trace_id",
            summary="trace had repeated write failures",
            confidence=1.1,
        )


def test_hypothesis_rejects_duplicate_evidence_ids() -> None:
    with pytest.raises(ValidationError, match="evidence ids must be unique"):
        Hypothesis(
            title="database write failed",
            description="persistence layer returned an error",
            supporting_evidence_ids=["evidence_1", "evidence_1"],
        )
