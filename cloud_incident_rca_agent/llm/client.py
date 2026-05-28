"""Provider-neutral LLM client boundary."""

from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from cloud_incident_rca_agent.domain import (
    ConfidenceLevel,
    Evidence,
    Hypothesis,
    Incident,
    InvestigationPlan,
    RCAReport,
)


class LLMClient(Protocol):
    """Provider-neutral structured reasoning contract."""

    async def normalize_incident(self, raw_description: str) -> Incident:
        """Return a normalized incident from raw user input."""

    async def classify_incident(self, incident: Incident) -> Incident:
        """Return the incident with issue category and signals populated."""

    async def create_plan(self, incident: Incident) -> InvestigationPlan:
        """Return a bounded investigation plan."""

    async def update_hypotheses(
        self,
        *,
        incident: Incident,
        existing_hypotheses: list[Hypothesis],
        evidence: list[Evidence],
    ) -> list[Hypothesis]:
        """Return updated candidate hypotheses."""

    async def build_report(
        self,
        *,
        incident: Incident,
        hypotheses: list[Hypothesis],
        evidence: list[Evidence],
        remaining_unknowns: list[str],
    ) -> RCAReport:
        """Return the final structured RCA report."""


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
                supporting_evidence=[],
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

    async def _parse_json_model(self, prompt: str, model_type: type[BaseModel]) -> BaseModel:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
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
        return await self._parse_json_model(prompt, Incident)  # type: ignore[return-value]

    async def classify_incident(self, incident: Incident) -> Incident:
        prompt = (
            "Classify this cloud incident and return JSON matching the Incident schema. "
            f"Incident: {incident.model_dump(mode='json')}"
        )
        return await self._parse_json_model(prompt, Incident)  # type: ignore[return-value]

    async def create_plan(self, incident: Incident) -> InvestigationPlan:
        prompt = (
            "Create a bounded cloud incident investigation plan as JSON matching the "
            f"InvestigationPlan schema. Incident: {incident.model_dump(mode='json')}"
        )
        return await self._parse_json_model(prompt, InvestigationPlan)  # type: ignore[return-value]

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
        result = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        payload = json.loads(result.choices[0].message.content or "{}")
        return [Hypothesis.model_validate(item) for item in payload.get("hypotheses", [])]

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
        return await self._parse_json_model(prompt, RCAReport)  # type: ignore[return-value]
