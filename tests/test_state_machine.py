import pytest

from cloud_incident_rca_agent.domain import Incident, InvestigationState, InvestigationStatus
from cloud_incident_rca_agent.orchestrator import (
    InvestigationStateMachine,
    StateTransitionError,
)


def test_state_machine_accepts_nominal_lifecycle() -> None:
    state = InvestigationState(incident=Incident(raw_description="orders API times out"))
    machine = InvestigationStateMachine()

    for next_state in [
        InvestigationStatus.CLASSIFY,
        InvestigationStatus.PLAN,
        InvestigationStatus.COLLECT_EVIDENCE,
        InvestigationStatus.UPDATE_HYPOTHESES,
        InvestigationStatus.VERIFY,
        InvestigationStatus.SUMMARIZE,
        InvestigationStatus.DONE,
    ]:
        machine.transition(state, next_state)

    assert state.current_state == InvestigationStatus.DONE
    assert machine.is_terminal(state.current_state)
    assert len(state.execution_log) == 7


def test_verify_can_loop_back_to_collect_more_evidence() -> None:
    state = InvestigationState(
        incident=Incident(raw_description="payment callback data mismatch")
    )
    machine = InvestigationStateMachine()

    for next_state in [
        InvestigationStatus.CLASSIFY,
        InvestigationStatus.PLAN,
        InvestigationStatus.COLLECT_EVIDENCE,
        InvestigationStatus.UPDATE_HYPOTHESES,
        InvestigationStatus.VERIFY,
        InvestigationStatus.COLLECT_EVIDENCE,
    ]:
        machine.transition(state, next_state)

    assert state.current_state == InvestigationStatus.COLLECT_EVIDENCE


def test_invalid_transition_raises_clear_error() -> None:
    state = InvestigationState(incident=Incident(raw_description="records missing"))
    machine = InvestigationStateMachine()

    with pytest.raises(StateTransitionError, match="INTAKE -> DONE"):
        machine.transition(state, InvestigationStatus.DONE)


def test_terminal_states_have_no_next_states() -> None:
    machine = InvestigationStateMachine()

    assert machine.next_states(InvestigationStatus.DONE) == frozenset()
    assert machine.next_states(InvestigationStatus.BLOCKED) == frozenset()
    assert machine.next_states(InvestigationStatus.FAILED) == frozenset()


def test_plan_can_enter_human_review_and_continue_when_approved() -> None:
    state = InvestigationState(incident=Incident(raw_description="checkout API returns 500"))
    machine = InvestigationStateMachine()

    for next_state in [
        InvestigationStatus.CLASSIFY,
        InvestigationStatus.PLAN,
        InvestigationStatus.HUMAN_REVIEW,
        InvestigationStatus.COLLECT_EVIDENCE,
    ]:
        machine.transition(state, next_state)

    assert state.current_state == InvestigationStatus.COLLECT_EVIDENCE


def test_human_review_rejection_can_return_to_plan() -> None:
    state = InvestigationState(incident=Incident(raw_description="payments are inconsistent"))
    machine = InvestigationStateMachine()

    for next_state in [
        InvestigationStatus.CLASSIFY,
        InvestigationStatus.PLAN,
        InvestigationStatus.HUMAN_REVIEW,
        InvestigationStatus.PLAN,
    ]:
        machine.transition(state, next_state)

    assert state.current_state == InvestigationStatus.PLAN


def test_human_review_can_block_when_approval_is_unavailable() -> None:
    state = InvestigationState(incident=Incident(raw_description="orders API times out"))
    machine = InvestigationStateMachine()

    for next_state in [
        InvestigationStatus.CLASSIFY,
        InvestigationStatus.PLAN,
        InvestigationStatus.HUMAN_REVIEW,
        InvestigationStatus.BLOCKED,
    ]:
        machine.transition(state, next_state)

    assert state.current_state == InvestigationStatus.BLOCKED
    assert machine.is_terminal(state.current_state)


def test_plan_origin_human_review_cannot_skip_to_done() -> None:
    state = InvestigationState(incident=Incident(raw_description="checkout API returns 500"))
    machine = InvestigationStateMachine()

    for next_state in [
        InvestigationStatus.CLASSIFY,
        InvestigationStatus.PLAN,
        InvestigationStatus.HUMAN_REVIEW,
    ]:
        machine.transition(state, next_state)

    with pytest.raises(StateTransitionError, match="HUMAN_REVIEW -> DONE"):
        machine.transition(state, InvestigationStatus.DONE)


def test_summarize_origin_human_review_cannot_return_to_plan() -> None:
    state = InvestigationState(incident=Incident(raw_description="orders API times out"))
    machine = InvestigationStateMachine()

    for next_state in [
        InvestigationStatus.CLASSIFY,
        InvestigationStatus.PLAN,
        InvestigationStatus.COLLECT_EVIDENCE,
        InvestigationStatus.UPDATE_HYPOTHESES,
        InvestigationStatus.VERIFY,
        InvestigationStatus.SUMMARIZE,
        InvestigationStatus.HUMAN_REVIEW,
    ]:
        machine.transition(state, next_state)

    with pytest.raises(StateTransitionError, match="HUMAN_REVIEW -> PLAN"):
        machine.transition(state, InvestigationStatus.PLAN)
