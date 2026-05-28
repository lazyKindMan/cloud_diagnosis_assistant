"""Inspection-only Chrome MCP connector."""

from __future__ import annotations

from cloud_incident_rca_agent.connectors.base import CallableMCPClient, evidence_from_payload
from cloud_incident_rca_agent.domain import EvidenceSource, ToolIntent, ToolResult


class ChromeMCPConnector:
    """Executes Chrome inspection intents and normalizes page observations."""

    def __init__(self, client: CallableMCPClient) -> None:
        self._client = client

    async def execute(self, intent: ToolIntent) -> ToolResult:
        payload = await self._client.call_tool(intent.tool_name, intent.parameters)
        summary = (
            payload.get("summary", "Chrome inspection returned evidence")
            if isinstance(payload, dict)
            else "Chrome inspection returned evidence"
        )
        evidence = evidence_from_payload(
            source=EvidenceSource.CHROME,
            tool_name=intent.tool_name,
            summary=summary,
            payload=payload,
            confidence=0.6,
            sensitive=intent.sensitive,
        )
        return ToolResult(intent_id=intent.intent_id, success=True, evidence=[evidence])
