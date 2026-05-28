"""Connector for cls-log-mcp evidence collection."""

from __future__ import annotations

from cloud_incident_rca_agent.connectors.base import CallableMCPClient, evidence_from_payload
from cloud_incident_rca_agent.domain import EvidenceSource, ToolIntent, ToolResult


class ClsLogMCPConnector:
    """Executes cls-log-mcp tool intents and normalizes log evidence."""

    def __init__(self, client: CallableMCPClient) -> None:
        self._client = client

    async def execute(self, intent: ToolIntent) -> ToolResult:
        payload = await self._client.call_tool(intent.tool_name, intent.parameters)
        summary = (
            payload.get("summary", "cls-log-mcp returned log evidence")
            if isinstance(payload, dict)
            else "cls-log-mcp returned log evidence"
        )
        trace_id = payload.get("trace_id") if isinstance(payload, dict) else None
        evidence = evidence_from_payload(
            source=EvidenceSource.CLS_LOG_MCP,
            tool_name=intent.tool_name,
            summary=summary,
            payload=payload,
            confidence=0.75,
            trace_id=trace_id,
            sensitive=intent.sensitive,
        )
        return ToolResult(intent_id=intent.intent_id, success=True, evidence=[evidence])
