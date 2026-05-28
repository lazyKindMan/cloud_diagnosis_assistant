"""Task-level LLM invocation service."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloud_incident_rca_agent.domain import Incident
from cloud_incident_rca_agent.llm import LLMClient


class LLMTask(StrEnum):
    """Supported one-shot LLM invocation tasks."""

    NORMALIZE = "normalize"
    CLASSIFY = "classify"
    PLAN = "plan"


class LLMInvokeRequest(BaseModel):
    """Input for one task-level LLM invocation."""

    model_config = ConfigDict(extra="forbid")

    task: LLMTask
    raw_description: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_non_empty_raw_description(self) -> "LLMInvokeRequest":
        if not self.raw_description.strip():
            raise ValueError("raw_description is required")
        return self


class LLMInvokeResult(BaseModel):
    """JSON-ready result of one LLM invocation."""

    model_config = ConfigDict(extra="forbid")

    task: LLMTask
    payload: dict[str, Any]


async def invoke_llm_task(
    llm_client: LLMClient,
    request: LLMInvokeRequest,
) -> LLMInvokeResult:
    """Invoke one supported LLM task and return a JSON-ready payload."""

    if request.task == LLMTask.NORMALIZE:
        incident = await llm_client.normalize_incident(request.raw_description)
        return LLMInvokeResult(task=request.task, payload=incident.model_dump(mode="json"))

    if request.task == LLMTask.CLASSIFY:
        incident = Incident(raw_description=request.raw_description)
        classified = await llm_client.classify_incident(incident)
        return LLMInvokeResult(task=request.task, payload=classified.model_dump(mode="json"))

    incident = Incident(raw_description=request.raw_description)
    plan = await llm_client.create_plan(incident)
    return LLMInvokeResult(task=request.task, payload=plan.model_dump(mode="json"))
