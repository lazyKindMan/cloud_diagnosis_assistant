import pytest

from cloud_incident_rca_agent.domain import (
    ConfidenceLevel,
    Hypothesis,
    Incident,
    InvestigationPlan,
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


class FakeOpenAIMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeOpenAIChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeOpenAIMessage(content)


class FakeOpenAIResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeOpenAIChoice(content)]


class RecordingChatCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeOpenAIResponse(self.content)


class RecordingChat:
    def __init__(self, content: str) -> None:
        self.completions = RecordingChatCompletions(content)


class RecordingOpenAIClient:
    def __init__(self, content: str) -> None:
        self.chat = RecordingChat(content)


@pytest.mark.asyncio
async def test_openai_client_invokes_api_and_validates_json_model() -> None:
    raw_json = """
    {
        "raw_description": "checkout API returns 500",
        "normalized_summary": "checkout API returns 500 in prod"
    }
    """
    sdk_client = RecordingOpenAIClient(raw_json)
    client = OpenAILLMClient(api_key=None, client=sdk_client, model="test-model")

    incident = await client.invoke_json(
        "normalize this incident",
        Incident,
    )

    assert incident.model_dump(exclude={"incident_id"}) == Incident(
        raw_description="checkout API returns 500",
        normalized_summary="checkout API returns 500 in prod",
    ).model_dump(exclude={"incident_id"})
    assert len(sdk_client.chat.completions.calls) == 1
    call = sdk_client.chat.completions.calls[0]
    assert call["model"] == "test-model"
    assert call["messages"][-1] == {"role": "user", "content": "normalize this incident"}
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["name"] == "Incident"
    assert call["response_format"]["json_schema"]["strict"] is True
    schema = call["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "raw_description" in schema["required"]
    assert "normalized_summary" in schema["required"]


@pytest.mark.asyncio
async def test_openai_client_uses_non_strict_schema_for_open_tool_parameters() -> None:
    raw_json = """
    {
        "summary": "Collect checkout API error logs.",
        "tool_intents": [
            {
                "target": "cls-log-mcp",
                "tool_name": "search_logs",
                "parameters": {"service": "checkout-api"},
                "purpose": "Find HTTP 500 log entries"
            }
        ],
        "max_tool_calls": 1,
        "stopping_criteria": ["one relevant error log found"],
        "requires_human_review": false,
        "review_reason": null
    }
    """
    sdk_client = RecordingOpenAIClient(raw_json)
    client = OpenAILLMClient(api_key=None, client=sdk_client, model="test-model")

    plan = await client.invoke_json("create an investigation plan", InvestigationPlan)

    assert plan.tool_intents[0].parameters == {"service": "checkout-api"}
    response_format = sdk_client.chat.completions.calls[0]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "InvestigationPlan"
    assert response_format["json_schema"]["strict"] is False


@pytest.mark.asyncio
async def test_openai_client_rejects_invalid_json_response() -> None:
    sdk_client = RecordingOpenAIClient("not json")
    client = OpenAILLMClient(api_key=None, client=sdk_client)

    with pytest.raises(ValueError, match="LLM output failed schema validation"):
        await client.invoke_json("normalize this incident", Incident)
