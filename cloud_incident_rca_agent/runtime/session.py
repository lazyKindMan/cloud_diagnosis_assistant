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

    def _path_for(self, session_id: str) -> Path:
        return self._storage_dir / f"{session_id}.json"

    def _write(self, session: AgentSession) -> None:
        self._path_for(session.session_id).write_text(
            session.model_dump_json(indent=2),
            encoding="utf-8",
        )
