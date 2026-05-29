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

        matches: list[dict[str, str]] = []
        for base in paths_or_error:
            for pattern in request.file_globs:
                paths = [base] if base.is_file() else base.rglob(pattern)
                for path in paths:
                    if len(matches) >= request.max_files:
                        break
                    if not path.is_file() or not self._is_readable_source(path):
                        continue
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    lowered = text.lower()
                    if not any(term.lower() in lowered for term in request.search_terms):
                        continue
                    matches.append(
                        {
                            "path": path.relative_to(self._root).as_posix(),
                            "snippet": text[: request.max_bytes_per_file],
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
        resolved: list[Path] = []
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
