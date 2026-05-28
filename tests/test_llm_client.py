import pytest

from cloud_incident_rca_agent.domain import (
    ConfidenceLevel,
    Hypothesis,
    Incident,
    RCAReport,
)
from cloud_incident_rca_agent.llm import FakeLLMClient, OpenAILLMClient


@pytest.mark.asyncio
async def test_fake_llm_normalizes_incident() -> None:
    client = FakeLLMClient()
    incident = await client.normalize_incident("checkout API returns 500 in prod")

    assert incident.raw_description == "checkout API returns 500 in prod"
    assert incident.normalized_summary == "checkout API returns 500 in prod"


@pytest.mark.asyncio
async def test_fake_llm_generates_hypotheses() -> None:
    client = FakeLLMClient()
    hypotheses = await client.update_hypotheses(
        incident=Incident(raw_description="checkout API returns 500"),
        existing_hypotheses=[],
        evidence=[],
    )

    assert len(hypotheses) == 1
    assert hypotheses[0].model_dump(exclude={"hypothesis_id"}) == Hypothesis(
        title="Insufficient evidence",
        description="The investigation needs more evidence before confirming a root cause.",
        missing_evidence=["logs", "database state", "recent deployment context"],
        confidence=0.1,
    ).model_dump(exclude={"hypothesis_id"})


@pytest.mark.asyncio
async def test_fake_llm_builds_report() -> None:
    client = FakeLLMClient()
    report = await client.build_report(
        incident=Incident(raw_description="checkout API returns 500"),
        hypotheses=[],
        evidence=[],
        remaining_unknowns=["no evidence collected"],
    )

    assert report == RCAReport(
        incident_summary="checkout API returns 500",
        most_likely_root_cause="Root cause not confirmed",
        confidence_level=ConfidenceLevel.LOW,
        supporting_evidence=[],
        ruled_out_alternatives=[],
        remaining_unknowns=["no evidence collected"],
        recommended_next_actions=["collect more evidence before remediation"],
    )


def test_openai_client_requires_api_key_or_client() -> None:
    with pytest.raises(ValueError, match="api_key or client"):
        OpenAILLMClient(api_key=None, client=None)
