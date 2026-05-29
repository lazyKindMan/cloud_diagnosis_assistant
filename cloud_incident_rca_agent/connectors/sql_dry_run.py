"""SQL dry-run safety validator."""

from __future__ import annotations

import re

from cloud_incident_rca_agent.domain import (
    ConnectorError,
    ConnectorErrorCategory,
    Evidence,
    EvidenceSource,
    SqlEvidenceRequest,
    SqlResultShape,
    ToolResult,
)

SENSITIVE_FIELD = re.compile(
    r"\b(password|passwd|token|secret|access_key|private_key|credential)\b",
    re.IGNORECASE,
)
DISALLOWED_SQL = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|replace|grant|revoke|"
    r"begin|commit|rollback|call|exec|execute|set)\b",
    re.IGNORECASE,
)


class SqlDryRunValidator:
    """Validates generated SQL and emits dry-run evidence."""

    async def execute(self, request: SqlEvidenceRequest) -> ToolResult:
        error = self.validate(request.sql, request.expected_result_shape)
        if error is not None:
            return ToolResult(
                intent_id=request.request_id,
                success=False,
                connector_error=ConnectorError(
                    category=ConnectorErrorCategory.POLICY,
                    message=error,
                ),
            )

        evidence = Evidence(
            source=EvidenceSource.MYSQL,
            tool_name="sql_dry_run",
            summary="SQL query is safe and ready for MySQL MCP execution",
            structured_data={
                "sql": request.sql,
                "tables": request.tables,
                "validation_purpose": request.validation_purpose,
                "interpretation_rule": request.interpretation_rule,
                "parameters": request.parameters,
            },
            confidence=0.5,
        )
        return ToolResult(intent_id=request.request_id, success=True, evidence=[evidence])

    def validate(self, sql: str, result_shape: SqlResultShape) -> str | None:
        stripped = sql.strip()
        lowered = stripped.lower()
        if ";" in stripped.rstrip(";"):
            return "multi-statement SQL is not allowed"
        if DISALLOWED_SQL.search(stripped):
            return "only SELECT or WITH queries are allowed"
        if not (lowered.startswith("select ") or lowered.startswith("with ")):
            return "only SELECT or WITH queries are allowed"
        if re.search(r"select\s+\*", lowered):
            return "SELECT * is not allowed"
        if SENSITIVE_FIELD.search(stripped):
            return "sensitive field is not allowed"

        is_aggregate = result_shape in {SqlResultShape.COUNT, SqlResultShape.AGGREGATE}
        if not is_aggregate and not re.search(r"\bwhere\b", lowered):
            return "non-aggregate queries require WHERE"
        if not is_aggregate and not re.search(r"\blimit\b", lowered):
            return "non-aggregate queries require LIMIT"
        return None
