"""Plain Python investigation state machine."""

from __future__ import annotations

from collections.abc import Mapping

from cloud_incident_rca_agent.domain.models import ExecutionLogEntry, InvestigationState
from cloud_incident_rca_agent.domain.types import InvestigationStatus


class StateTransitionError(ValueError):
    """Raised when an invalid investigation state transition is requested."""


class InvestigationStateMachine:
    """Validates and applies the bounded RCA lifecycle transitions."""

    TERMINAL_STATES = frozenset(
        {
            InvestigationStatus.DONE,
            InvestigationStatus.BLOCKED,
            InvestigationStatus.FAILED,
        }
    )

    DEFAULT_TRANSITIONS: Mapping[InvestigationStatus, frozenset[InvestigationStatus]] = {
        InvestigationStatus.INTAKE: frozenset(
            {
                InvestigationStatus.CLASSIFY,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.CLASSIFY: frozenset(
            {
                InvestigationStatus.PLAN,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.PLAN: frozenset(
            {
                InvestigationStatus.COLLECT_EVIDENCE,
                InvestigationStatus.HUMAN_REVIEW,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.COLLECT_EVIDENCE: frozenset(
            {
                InvestigationStatus.UPDATE_HYPOTHESES,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.UPDATE_HYPOTHESES: frozenset(
            {
                InvestigationStatus.VERIFY,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.VERIFY: frozenset(
            {
                InvestigationStatus.COLLECT_EVIDENCE,
                InvestigationStatus.HUMAN_REVIEW,
                InvestigationStatus.SUMMARIZE,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.HUMAN_REVIEW: frozenset(
            {
                InvestigationStatus.PLAN,
                InvestigationStatus.COLLECT_EVIDENCE,
                InvestigationStatus.SUMMARIZE,
                InvestigationStatus.DONE,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.SUMMARIZE: frozenset(
            {
                InvestigationStatus.HUMAN_REVIEW,
                InvestigationStatus.DONE,
                InvestigationStatus.BLOCKED,
                InvestigationStatus.FAILED,
            }
        ),
        InvestigationStatus.DONE: frozenset(),
        InvestigationStatus.BLOCKED: frozenset(),
        InvestigationStatus.FAILED: frozenset(),
    }

    def __init__(
        self,
        transitions: Mapping[InvestigationStatus, frozenset[InvestigationStatus]]
        | None = None,
    ) -> None:
        self._transitions = transitions or self.DEFAULT_TRANSITIONS

    def next_states(self, current_state: InvestigationStatus) -> frozenset[InvestigationStatus]:
        return self._transitions.get(current_state, frozenset())

    def is_terminal(self, state: InvestigationStatus) -> bool:
        return state in self.TERMINAL_STATES

    def can_transition(
        self,
        current_state: InvestigationStatus,
        next_state: InvestigationStatus,
    ) -> bool:
        return next_state in self.next_states(current_state)

    def require_transition(
        self,
        current_state: InvestigationStatus,
        next_state: InvestigationStatus,
    ) -> None:
        if self.can_transition(current_state, next_state):
            return

        allowed = ", ".join(sorted(state.value for state in self.next_states(current_state)))
        if not allowed:
            allowed = "no further states"
        raise StateTransitionError(
            f"invalid transition {current_state.value} -> {next_state.value}; "
            f"allowed: {allowed}"
        )

    def transition(
        self,
        investigation: InvestigationState,
        next_state: InvestigationStatus,
        *,
        message: str | None = None,
    ) -> InvestigationState:
        """Apply a validated transition to an investigation state."""

        self.require_transition(investigation.current_state, next_state)
        investigation.current_state = next_state
        investigation.execution_log.append(
            ExecutionLogEntry(
                state=next_state,
                message=message or f"Transitioned to {next_state.value}",
            )
        )
        return investigation
