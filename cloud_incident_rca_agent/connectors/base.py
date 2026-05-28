"""Shared connector contracts."""

from __future__ import annotations

from typing import Any, Protocol

from cloud_incident_rca_agent.domain import Evidence, ToolIntent, ToolResult


class CallableMCPClient(Protocol):
    """Small adapter protocol for MCP clients used by connectors."""

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call one MCP tool and return the raw tool payload."""


class MCPConnector(Protocol):
    """Connector that executes one typed tool intent."""

    async def execute(self, intent: ToolIntent) -> ToolResult:
        """Execute the intent and return normalized evidence or a connector error."""


def evidence_from_payload(
    *,
    source,
    tool_name: str,
    summary: str,
    payload: Any,
    confidence: float = 0.5,
    trace_id: str | None = None,
    sensitive: bool = False,
) -> Evidence:
    """Normalize an MCP payload into one Evidence object."""

    structured_data = payload if isinstance(payload, dict) else {"raw": payload}
    return Evidence(
        source=source,
        tool_name=tool_name,
        summary=summary,
        structured_data=structured_data,
        confidence=confidence,
        trace_id=trace_id,
        sensitive=sensitive,
    )
