import pytest

from cloud_incident_rca_agent.domain import AgentSessionStatus
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
