import pytest

from cloud_incident_rca_agent.connectors import (
    CallableMCPClient,
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
