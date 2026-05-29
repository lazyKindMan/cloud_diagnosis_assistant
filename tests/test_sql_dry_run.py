import pytest

from cloud_incident_rca_agent.connectors import SqlDryRunValidator
from cloud_incident_rca_agent.domain import (
    ConnectorErrorCategory,
    SqlEvidenceRequest,
    SqlResultShape,
)


def make_request(sql: str) -> SqlEvidenceRequest:
    return SqlEvidenceRequest(
        hypothesis_ref="orders duplicate",
        question="Check duplicate rows",
        expected_signal="bounded rows",
        schema_context={"orders": ["id", "status", "created_at"]},
        validation_purpose="Check duplicate order rows",
        tables=["orders"],
        sql=sql,
        parameters={"id": "ord_1"},
        expected_result_shape=SqlResultShape.ROWS,
        interpretation_rule="More than one row supports duplicate persistence hypothesis",
        safety_notes="Single table, bounded by order id and limit",
    )


@pytest.mark.asyncio
async def test_sql_dry_run_accepts_safe_select() -> None:
    result = await SqlDryRunValidator().execute(
        make_request("select id, status from orders where id = :id limit 10")
    )

    assert result.success is True
    assert result.evidence[0].tool_name == "sql_dry_run"
    assert result.evidence[0].structured_data["sql"].startswith("select id")


@pytest.mark.parametrize(
    ("sql", "reason"),
    [
        ("select * from orders where id = :id limit 10", "SELECT * is not allowed"),
        ("select id from orders", "non-aggregate queries require WHERE"),
        ("select id from orders where id = :id", "non-aggregate queries require LIMIT"),
        ("update orders set status = 'paid'", "only SELECT or WITH queries are allowed"),
        (
            "select id from orders where id = :id; select id from users",
            "multi-statement SQL is not allowed",
        ),
        (
            "select password from users where id = :id limit 1",
            "sensitive field is not allowed",
        ),
    ],
)
@pytest.mark.asyncio
async def test_sql_dry_run_rejects_unsafe_sql(sql: str, reason: str) -> None:
    result = await SqlDryRunValidator().execute(make_request(sql))

    assert result.success is False
    assert result.connector_error is not None
    assert result.connector_error.category == ConnectorErrorCategory.POLICY
    assert reason in result.connector_error.message
