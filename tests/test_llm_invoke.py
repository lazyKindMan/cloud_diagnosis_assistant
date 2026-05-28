import pytest

from cloud_incident_rca_agent.domain import InvestigationPlan
from cloud_incident_rca_agent.llm import FakeLLMClient
from cloud_incident_rca_agent.runtime import LLMInvokeRequest, LLMTask, invoke_llm_task


@pytest.mark.asyncio
async def test_invoke_normalize_task_returns_json_ready_payload() -> None:
    result = await invoke_llm_task(
        FakeLLMClient(),
        LLMInvokeRequest(
            task=LLMTask.NORMALIZE,
            raw_description="checkout API returns 500",
        ),
    )

    assert result.task == LLMTask.NORMALIZE
    assert result.payload["raw_description"] == "checkout API returns 500"
    assert result.payload["normalized_summary"] == "checkout API returns 500"


@pytest.mark.asyncio
async def test_invoke_plan_task_returns_investigation_plan_payload() -> None:
    result = await invoke_llm_task(
        FakeLLMClient(),
        LLMInvokeRequest(
            task=LLMTask.PLAN,
            raw_description="checkout API returns 500",
        ),
    )

    plan = InvestigationPlan.model_validate(result.payload)
    assert plan.summary == "Collect log evidence for the reported incident."
    assert plan.tool_intents[0].tool_name == "search_logs_by_trace_id"


def test_invoke_request_requires_raw_description() -> None:
    with pytest.raises(ValueError, match="raw_description"):
        LLMInvokeRequest(task=LLMTask.NORMALIZE, raw_description="")
