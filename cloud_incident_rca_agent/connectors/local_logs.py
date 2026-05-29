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
            return self._error(
                request.request_id,
                f"local log file not found: {request.local_path_hint}",
            )

        matches: list[str] = []
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            lowered = line.lower()
            if request.trace_id and request.trace_id not in line:
                continue
            if request.keywords and not all(
                keyword.lower() in lowered for keyword in request.keywords
            ):
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
