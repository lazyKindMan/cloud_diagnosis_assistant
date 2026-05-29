"""Dispatch evidence requests to configured execution routes."""

from __future__ import annotations

from typing import Any

from cloud_incident_rca_agent.connectors import SqlDryRunValidator
from cloud_incident_rca_agent.domain import (
    CodeEvidenceRequest,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    LogEvidenceRequest,
    LogEvidenceRoute,
    SqlEvidenceRequest,
    ToolResult,
)


class EvidenceExecutor:
    """Executes evidence requests through local or configured connectors."""

    def __init__(
        self,
        *,
        code_inspector: Any = None,
        local_log_inspector: Any = None,
        cls_connector: Any = None,
        chrome_connector: Any = None,
        sql_validator: SqlDryRunValidator | None = None,
    ) -> None:
        self._code_inspector = code_inspector
        self._local_log_inspector = local_log_inspector
        self._cls_connector = cls_connector
        self._chrome_connector = chrome_connector
        self._sql_validator = sql_validator or SqlDryRunValidator()

    async def execute(self, request: Any) -> EvidenceRequestResult:
        if isinstance(request, CodeEvidenceRequest):
            return await self._execute_with(
                "code inspector is not configured",
                request,
                self._code_inspector,
            )
        if isinstance(request, SqlEvidenceRequest):
            return self._from_tool_result(await self._sql_validator.execute(request))
        if isinstance(request, LogEvidenceRequest):
            if request.route == LogEvidenceRoute.LOCAL_FILE:
                return await self._execute_with(
                    "local log inspector is not configured",
                    request,
                    self._local_log_inspector,
                )
            if request.route == LogEvidenceRoute.CLS_MCP:
                return await self._execute_with(
                    "cls-log-mcp connector is not configured",
                    request,
                    self._cls_connector,
                )
            return await self._execute_with(
                "chrome MCP connector is not configured",
                request,
                self._chrome_connector,
            )
        return EvidenceRequestResult(
            request_id=request.request_id,
            success=False,
            status=EvidenceRequestStatus.FAILED,
            message="unsupported evidence request type",
        )

    async def _execute_with(
        self,
        missing_message: str,
        request: Any,
        connector: Any,
    ) -> EvidenceRequestResult:
        if connector is None:
            return EvidenceRequestResult(
                request_id=request.request_id,
                success=False,
                status=EvidenceRequestStatus.SKIPPED,
                message=missing_message,
            )
        return self._from_tool_result(await connector.execute(request))

    def _from_tool_result(self, result: ToolResult) -> EvidenceRequestResult:
        return EvidenceRequestResult(
            request_id=result.intent_id,
            success=result.success,
            evidence=result.evidence,
            status=(
                EvidenceRequestStatus.EXECUTED
                if result.success
                else EvidenceRequestStatus.FAILED
            ),
            message=(
                "evidence request executed"
                if result.success
                else result.connector_error.message
            ),
            connector_error=result.connector_error,
        )
