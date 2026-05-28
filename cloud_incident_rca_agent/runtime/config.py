"""Runtime configuration for LLM-backed workflows."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloud_incident_rca_agent.llm import FakeLLMClient, LLMClient, OpenAILLMClient


class LLMProvider(StrEnum):
    """Supported runtime LLM providers."""

    FAKE = "fake"
    OPENAI = "openai"


class LLMRuntimeSettings(BaseModel):
    """Settings required to create an LLM client."""

    model_config = ConfigDict(extra="forbid")

    provider: LLMProvider = LLMProvider.FAKE
    openai_api_key: str | None = None
    openai_model: str = Field(default="gpt-4.1-mini", min_length=1)

    @model_validator(mode="after")
    def require_openai_key_for_openai_provider(self) -> "LLMRuntimeSettings":
        if self.provider == LLMProvider.OPENAI and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when CLOUD_RCA_LLM_PROVIDER=openai")
        return self


def llm_settings_from_env(environ: dict[str, str] | None = None) -> LLMRuntimeSettings:
    """Build LLM runtime settings from environment variables."""

    source = os.environ if environ is None else environ
    return LLMRuntimeSettings(
        provider=LLMProvider(source.get("CLOUD_RCA_LLM_PROVIDER", LLMProvider.FAKE.value)),
        openai_api_key=source.get("OPENAI_API_KEY"),
        openai_model=source.get("OPENAI_MODEL", "gpt-4.1-mini"),
    )


def build_llm_client(
    settings: LLMRuntimeSettings,
    *,
    openai_client: Any | None = None,
) -> LLMClient:
    """Create the configured LLM client."""

    if settings.provider == LLMProvider.FAKE:
        return FakeLLMClient()
    return OpenAILLMClient(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        client=openai_client,
    )
