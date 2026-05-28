import pytest

from cloud_incident_rca_agent.connectors import (
    CallableMCPClient,
    ChromeMCPConnector,
    ClsLogMCPConnector,
    MySQLMCPConnector,
    is_read_only_sql,
)
from cloud_incident_rca_agent.domain import ToolIntent, ToolTarget


class RecordingMCPClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def call_tool(self, tool_name: str, arguments: dict):
        self.calls.append((tool_name, arguments))
        return self.response


def test_sql_guard_accepts_single_select() -> None:
    assert is_read_only_sql("select id, status from orders where id = 1") is True


@pytest.mark.parametrize(
    "sql",
    [
        "update orders set status = 'paid'",
        "delete from orders",
        "drop table orders",
        "select * from orders; select * from payments",
        "begin; select * from orders",
    ],
)
def test_sql_guard_rejects_mutating_or_ambiguous_sql(sql: str) -> None:
    assert is_read_only_sql(sql) is False


@pytest.mark.asyncio
async def test_mysql_connector_rejects_write_query_before_calling_client() -> None:
    client = RecordingMCPClient(response={})
    connector = MySQLMCPConnector(client)
    result = await connector.execute(
        ToolIntent(
            target=ToolTarget.MYSQL,
            tool_name="query",
            parameters={"sql": "update orders set status = 'paid'"},
            purpose="verify state",
        )
    )

    assert result.success is False
    assert result.connector_error is not None
    assert result.connector_error.category == "policy"
    assert client.calls == []


@pytest.mark.asyncio
async def test_cls_log_connector_normalizes_payload_to_evidence() -> None:
    client = RecordingMCPClient(
        response={
            "summary": "trace had repeated persistence failures",
            "trace_id": "trace-123",
            "events": [{"level": "ERROR", "message": "write failed"}],
        }
    )
    connector = ClsLogMCPConnector(client)
    result = await connector.execute(
        ToolIntent(
            target=ToolTarget.CLS_LOG_MCP,
            tool_name="search_logs_by_trace_id",
            parameters={"trace_id": "trace-123"},
            purpose="inspect logs",
        )
    )

    assert result.success is True
    assert result.evidence[0].source == "cls-log-mcp"
    assert result.evidence[0].trace_id == "trace-123"
    assert result.evidence[0].summary == "trace had repeated persistence failures"


@pytest.mark.asyncio
async def test_chrome_connector_normalizes_inspection_payload() -> None:
    client = RecordingMCPClient(
        response={
            "summary": "deployment panel shows config changed",
            "url": "https://console.example/deployments",
        }
    )
    connector = ChromeMCPConnector(client)
    result = await connector.execute(
        ToolIntent(
            target=ToolTarget.CHROME,
            tool_name="inspect_page",
            parameters={"url": "https://console.example/deployments"},
            purpose="inspect deployment state",
        )
    )

    assert result.success is True
    assert result.evidence[0].source == "Chrome"
    assert result.evidence[0].summary == "deployment panel shows config changed"
