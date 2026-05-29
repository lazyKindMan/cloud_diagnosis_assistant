"""Provider-neutral LLM client boundary."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from cloud_incident_rca_agent.domain import (
    ConfidenceLevel,
    ContextPacket,
    Evidence,
    EvidenceAcquisitionPlan,
    Hypothesis,
    Incident,
    InvestigationPlan,
    RCAReport,
)

TModel = TypeVar("TModel", bound=BaseModel)


class LLMClient(Protocol):
    """Provider-neutral structured reasoning contract."""

    async def normalize_incident(self, raw_description: str) -> Incident:
        """Return a normalized incident from raw user input."""
        ...

    async def classify_incident(self, incident: Incident) -> Incident:
        """Return the incident with issue category and signals populated."""
        ...

    async def create_plan(self, incident: Incident) -> InvestigationPlan:
        """Return a bounded investigation plan."""
        ...

    async def create_evidence_plan(self, context: ContextPacket) -> EvidenceAcquisitionPlan:
        """Return a bounded evidence acquisition plan for the current session context."""
        ...

    async def update_hypotheses(
        self,
        *,
        incident: Incident,
        existing_hypotheses: list[Hypothesis],
        evidence: list[Evidence],
    ) -> list[Hypothesis]:
        """Return updated candidate hypotheses."""
        ...

    async def build_report(
        self,
        *,
        incident: Incident,
        hypotheses: list[Hypothesis],
        evidence: list[Evidence],
        remaining_unknowns: list[str],
    ) -> RCAReport:
        """Return the final structured RCA report."""
        ...


class _HypothesisListPayload(BaseModel):
    hypotheses: list[Hypothesis]


def _strict_json_schema(model_type: type[BaseModel]) -> dict[str, Any]:
    """Return the JSON schema subset accepted by OpenAI strict structured outputs."""

    schema = deepcopy(model_type.model_json_schema())
    return _ensure_strict_json_schema(schema)


def _ensure_strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)

    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)
        for property_schema in properties.values():
            if isinstance(property_schema, dict):
                _ensure_strict_json_schema(property_schema)

    defs = schema.get("$defs")
    if isinstance(defs, dict):
        for def_schema in defs.values():
            if isinstance(def_schema, dict):
                _ensure_strict_json_schema(def_schema)

    items = schema.get("items")
    if isinstance(items, dict):
        _ensure_strict_json_schema(items)

    any_of = schema.get("anyOf")
    if isinstance(any_of, list):
        for variant in any_of:
            if isinstance(variant, dict):
                _ensure_strict_json_schema(variant)

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for variant in all_of:
            if isinstance(variant, dict):
                _ensure_strict_json_schema(variant)

    if schema.get("default") is None:
        schema.pop("default", None)

    return schema


def _has_open_object_schema(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False

    additional_properties = schema.get("additionalProperties")
    if additional_properties is True or isinstance(additional_properties, dict):
        return True

    for nested_key in ("properties", "$defs", "definitions"):
        nested = schema.get(nested_key)
        if isinstance(nested, dict) and any(
            _has_open_object_schema(item) for item in nested.values()
        ):
            return True

    items = schema.get("items")
    if _has_open_object_schema(items):
        return True

    for nested_key in ("anyOf", "allOf"):
        nested = schema.get(nested_key)
        if isinstance(nested, list) and any(_has_open_object_schema(item) for item in nested):
            return True

    return False


def _response_schema_name(model_type: type[BaseModel]) -> str:
    name = model_type.__name__.strip("_") or "StructuredPayload"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:64]


def _response_format_for(model_type: type[BaseModel]) -> dict[str, Any]:
    schema = model_type.model_json_schema()
    strict = not _has_open_object_schema(schema)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _response_schema_name(model_type),
            "schema": _strict_json_schema(model_type) if strict else schema,
            "strict": strict,
        },
    }


class FakeLLMClient:
    """Deterministic LLM substitute for unit tests."""

    async def normalize_incident(self, raw_description: str) -> Incident:
        return Incident(
            raw_description=raw_description,
            normalized_summary=raw_description,
            missing_context=["time window", "service owner"] if raw_description else [],
        )

    async def classify_incident(self, incident: Incident) -> Incident:
        incident.issue_category = incident.issue_category or "unknown"
        return incident

    async def create_plan(self, incident: Incident) -> InvestigationPlan:
        from cloud_incident_rca_agent.domain import ToolIntent, ToolTarget

        return InvestigationPlan(
            summary="Collect log evidence for the reported incident.",
            tool_intents=[
                ToolIntent(
                    target=ToolTarget.CLS_LOG_MCP,
                    tool_name="search_logs_by_trace_id",
                    parameters={},
                    purpose="find error logs related to the incident",
                )
            ],
            max_tool_calls=1,
            stopping_criteria=["one relevant evidence item collected"],
        )

    async def create_evidence_plan(self, context: ContextPacket) -> EvidenceAcquisitionPlan:
        from cloud_incident_rca_agent.domain import CodeEvidenceRequest

        return EvidenceAcquisitionPlan(
            round_number=1,
            objective="Collect bounded code, log, or SQL evidence for the incident.",
            requests=[
                CodeEvidenceRequest(
                    hypothesis_ref="initial code path hypothesis",
                    question="Which local code path is most related to the incident?",
                    expected_signal="Relevant handler, service, or repository code",
                    search_terms=[context.incident_summary.split()[0]],
                    path_allowlist=["cloud_incident_rca_agent"],
                    file_globs=["*.py"],
                )
            ],
            max_requests=1,
            stop_conditions=["one bounded evidence request completes"],
        )

    async def update_hypotheses(
        self,
        *,
        incident: Incident,
        existing_hypotheses: list[Hypothesis],
        evidence: list[Evidence],
    ) -> list[Hypothesis]:
        if evidence:
            first = evidence[0]
            return [
                Hypothesis(
                    title="Evidence-backed service failure",
                    description=first.summary,
                    supporting_evidence_ids=[first.evidence_id],
                    confidence=0.7,
                )
            ]
        return [
            Hypothesis(
                title="Insufficient evidence",
                description="The investigation needs more evidence before confirming a root cause.",
                missing_evidence=["logs", "database state", "recent deployment context"],
                confidence=0.1,
            )
        ]

    async def build_report(
        self,
        *,
        incident: Incident,
        hypotheses: list[Hypothesis],
        evidence: list[Evidence],
        remaining_unknowns: list[str],
    ) -> RCAReport:
        top = max(hypotheses, key=lambda item: item.confidence, default=None)
        if top is None:
            return RCAReport(
                incident_summary=incident.normalized_summary or incident.raw_description,
                most_likely_root_cause="Root cause not confirmed",
                confidence_level=ConfidenceLevel.LOW,
                supporting_evidence=[item.summary for item in evidence if not item.sensitive],
                ruled_out_alternatives=[],
                remaining_unknowns=remaining_unknowns,
                recommended_next_actions=["collect more evidence before remediation"],
            )
        confidence = ConfidenceLevel.HIGH if top.confidence >= 0.8 else ConfidenceLevel.MEDIUM
        return RCAReport(
            incident_summary=incident.normalized_summary or incident.raw_description,
            most_likely_root_cause=top.description,
            confidence_level=confidence,
            supporting_evidence=[item.summary for item in evidence if not item.sensitive],
            ruled_out_alternatives=[],
            remaining_unknowns=remaining_unknowns,
            recommended_next_actions=["review supporting evidence before remediation"],
        )


class OpenAILLMClient:
    """OpenAI-backed implementation behind the provider-neutral LLM boundary."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-4.1-mini",
        client: Any | None = None,
    ) -> None:
        if client is None and not api_key:
            raise ValueError("api_key or client is required")
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key)
        self._client = client
        self._model = model

    async def invoke_json(self, prompt: str, model_type: type[TModel]) -> TModel:
        """Invoke the OpenAI API and validate the JSON response as a Pydantic model."""

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only JSON matching the provided response schema. "
                        "Use null or empty arrays when information is unavailable."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=_response_format_for(model_type),
        )
        text = response.choices[0].message.content or "{}"
        try:
            payload = json.loads(text)
            return model_type.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"LLM output failed schema validation: {exc}") from exc

    async def normalize_incident(self, raw_description: str) -> Incident:
        prompt = (
            "Normalize this cloud incident into JSON matching the Incident schema. "
            f"Raw description: {raw_description}"
        )
        return await self.invoke_json(prompt, Incident)

    async def classify_incident(self, incident: Incident) -> Incident:
        prompt = (
            "Classify this cloud incident and return JSON matching the Incident schema. "
            f"Incident: {incident.model_dump(mode='json')}"
        )
        return await self.invoke_json(prompt, Incident)

    async def create_plan(self, incident: Incident) -> InvestigationPlan:
        prompt = (
            "Create a bounded cloud incident investigation plan as JSON matching the "
            f"InvestigationPlan schema. Incident: {incident.model_dump(mode='json')}"
        )
        return await self.invoke_json(prompt, InvestigationPlan)

    async def create_evidence_plan(self, context: ContextPacket) -> EvidenceAcquisitionPlan:
        prompt = (
            "Create a bounded evidence acquisition plan as JSON matching the "
            "EvidenceAcquisitionPlan schema. Do not request broad searches. "
            f"Context: {context.model_dump(mode='json')}"
        )
        return await self.invoke_json(prompt, EvidenceAcquisitionPlan)

    async def update_hypotheses(
        self,
        *,
        incident: Incident,
        existing_hypotheses: list[Hypothesis],
        evidence: list[Evidence],
    ) -> list[Hypothesis]:
        prompt = (
            "Update RCA hypotheses and return a JSON object with a hypotheses array. "
            f"Incident: {incident.model_dump(mode='json')}. "
            f"Existing hypotheses: {[item.model_dump(mode='json') for item in existing_hypotheses]}. "
            f"Evidence: {[item.model_dump(mode='json') for item in evidence]}."
        )
        result = await self.invoke_json(prompt, _HypothesisListPayload)
        return result.hypotheses

    async def build_report(
        self,
        *,
        incident: Incident,
        hypotheses: list[Hypothesis],
        evidence: list[Evidence],
        remaining_unknowns: list[str],
    ) -> RCAReport:
        prompt = (
            "Build an evidence-backed RCA report as JSON matching the RCAReport schema. "
            f"Incident: {incident.model_dump(mode='json')}. "
            f"Hypotheses: {[item.model_dump(mode='json') for item in hypotheses]}. "
            f"Evidence summaries: {[item.summary for item in evidence]}. "
            f"Remaining unknowns: {remaining_unknowns}."
        )
        return await self.invoke_json(prompt, RCAReport)
