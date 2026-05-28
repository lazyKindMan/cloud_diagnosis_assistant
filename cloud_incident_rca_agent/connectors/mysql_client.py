"""Read-only MySQL MCP connector."""

from __future__ import annotations

import re

from cloud_incident_rca_agent.connectors.base import CallableMCPClient, evidence_from_payload
from cloud_incident_rca_agent.domain import (
    ConnectorError,
    ConnectorErrorCategory,
    EvidenceSource,
    ToolIntent,
    ToolResult,
)

_DISALLOWED_SQL = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|replace|grant|revoke|"
    r"begin|commit|rollback|call|exec|execute|set)\b",
    re.IGNORECASE,
)


def is_read_only_sql(sql: str) -> bool:
    """Return True only for a single read-only SELECT or WITH query."""

    stripped = sql.strip()
    if not stripped:
        return False
    if ";" in stripped.rstrip(";"):
        return False
    lowered = stripped.lower()
    if not (lowered.startswith("select ") or lowered.startswith("with ")):
        return False
    return _DISALLOWED_SQL.search(stripped) is None


class MySQLMCPConnector:
    """Executes read-only MySQL MCP tool intents."""

    def __init__(self, client: CallableMCPClient) -> None:
        self._client = client

    async def execute(self, intent: ToolIntent) -> ToolResult:
        sql = str(intent.parameters.get("sql", ""))
        if not is_read_only_sql(sql):
            return ToolResult(
                intent_id=intent.intent_id,
                success=False,
                connector_error=ConnectorError(
                    category=ConnectorErrorCategory.POLICY,
                    message="MySQL connector only allows a single read-only SELECT or WITH query",
                ),
            )

        payload = await self._client.call_tool(intent.tool_name, intent.parameters)
        evidence = evidence_from_payload(
            source=EvidenceSource.MYSQL,
            tool_name=intent.tool_name,
            summary="MySQL read-only query returned data",
            payload=payload,
            confidence=0.7,
            sensitive=intent.sensitive,
        )
        return ToolResult(intent_id=intent.intent_id, success=True, evidence=[evidence])
