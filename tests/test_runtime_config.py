import pytest

from cloud_incident_rca_agent.llm import FakeLLMClient, OpenAILLMClient
from cloud_incident_rca_agent.runtime import (
    LLMProvider,
    LLMRuntimeSettings,
    build_llm_client,
    llm_settings_from_env,
)


def test_llm_settings_default_to_fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUD_RCA_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    settings = llm_settings_from_env()

    assert settings == LLMRuntimeSettings(
        provider=LLMProvider.FAKE,
        openai_api_key=None,
        openai_model="gpt-4.1-mini",
    )


def test_llm_settings_read_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RCA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    settings = llm_settings_from_env()

    assert settings.provider == LLMProvider.OPENAI
    assert settings.openai_api_key == "sk-test"
    assert settings.openai_model == "gpt-test"


def test_openai_settings_require_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        LLMRuntimeSettings(provider=LLMProvider.OPENAI, openai_api_key=None)


def test_openai_settings_reject_blank_api_key() -> None:
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMRuntimeSettings(provider=LLMProvider.OPENAI, openai_api_key="   ")


def test_llm_settings_reject_blank_openai_model() -> None:
    with pytest.raises(ValueError, match="OPENAI_MODEL"):
        LLMRuntimeSettings(openai_model="   ")


def test_build_llm_client_returns_fake_client_by_default() -> None:
    client = build_llm_client(LLMRuntimeSettings(provider=LLMProvider.FAKE))

    assert isinstance(client, FakeLLMClient)


def test_build_llm_client_returns_openai_client_with_injected_sdk_client() -> None:
    sdk_client = object()
    client = build_llm_client(
        LLMRuntimeSettings(
            provider=LLMProvider.OPENAI,
            openai_api_key="sk-test",
            openai_model="gpt-test",
        ),
        openai_client=sdk_client,
    )

    assert isinstance(client, OpenAILLMClient)
    assert client._client is sdk_client
    assert client._model == "gpt-test"
