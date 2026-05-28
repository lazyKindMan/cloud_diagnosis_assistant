import os

import pytest

from cloud_incident_rca_agent.connectors import MySQLMCPConnector
from cloud_incident_rca_agent.domain import ToolIntent, ToolTarget
from cloud_incident_rca_agent.llm import OpenAILLMClient


pytestmark = pytest.mark.integration


class EnvMCPClient:
    async def call_tool(self, tool_name: str, arguments: dict):
        raise RuntimeError(
            "Configure a real MCP client adapter before enabling live MCP smoke tests"
        )


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY is required for live OpenAI smoke test",
)
@pytest.mark.asyncio
async def test_live_openai_client_normalizes_incident() -> None:
    client = OpenAILLMClient(api_key=os.environ["OPENAI_API_KEY"])
    incident = await client.normalize_incident("checkout API returns 500 in prod")

    assert incident.raw_description
    assert incident.normalized_summary


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_MCP_TESTS") != "1",
    reason="RUN_LIVE_MCP_TESTS=1 is required for live MCP smoke tests",
)
@pytest.mark.asyncio
async def test_live_mysql_connector_requires_real_mcp_adapter() -> None:
    connector = MySQLMCPConnector(EnvMCPClient())
    with pytest.raises(RuntimeError, match="real MCP client adapter"):
        await connector.execute(
            ToolIntent(
                target=ToolTarget.MYSQL,
                tool_name="query",
                parameters={"sql": "select 1"},
                purpose="smoke test read-only query",
            )
        )
