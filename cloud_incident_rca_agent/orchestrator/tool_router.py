"""Routes tool intents to MCP connectors."""

from __future__ import annotations

from cloud_incident_rca_agent.connectors import MCPConnector
from cloud_incident_rca_agent.domain import (
    ConnectorError,
    ConnectorErrorCategory,
    ToolIntent,
    ToolResult,
    ToolTarget,
)


class ToolRouter:
    """Executes tool intents through registered connectors."""

    def __init__(self, connectors: dict[ToolTarget, MCPConnector]) -> None:
        self._connectors = connectors

    async def execute(self, intent: ToolIntent) -> ToolResult:
        connector = self._connectors.get(intent.target)
        if connector is None:
            return ToolResult(
                intent_id=intent.intent_id,
                success=False,
                connector_error=ConnectorError(
                    category=ConnectorErrorCategory.PERMANENT,
                    message=f"no connector registered for {intent.target.value}",
                ),
            )
        try:
            return await connector.execute(intent)
        except TimeoutError as exc:
            return ToolResult(
                intent_id=intent.intent_id,
                success=False,
                connector_error=ConnectorError(
                    category=ConnectorErrorCategory.TRANSIENT,
                    message=str(exc) or "connector timed out",
                ),
            )
        except ValueError as exc:
            return ToolResult(
                intent_id=intent.intent_id,
                success=False,
                connector_error=ConnectorError(
                    category=ConnectorErrorCategory.SEMANTIC,
                    message=str(exc),
                ),
            )
