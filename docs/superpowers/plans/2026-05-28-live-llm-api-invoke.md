# Live LLM API Invoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small runtime surface that can invoke the existing `LLMClient` boundary from configuration and a CLI, using fake LLMs by default and OpenAI only when explicitly selected.

**Architecture:** Keep provider-specific behavior inside `cloud_incident_rca_agent.llm`. Add a runtime layer that creates an `LLMClient` from explicit settings or environment variables, then expose a task-level invocation service and console script. Unit tests use fake SDK clients and monkeypatched environment; live OpenAI remains behind skipped integration tests.

**Tech Stack:** Python 3.12+, Pydantic v2, pytest, pytest-asyncio, OpenAI Python SDK behind optional `integrations` extra.

---

## File Structure

- Create: `cloud_incident_rca_agent/runtime/__init__.py`
  - Export runtime configuration and invocation helpers.
- Create: `cloud_incident_rca_agent/runtime/config.py`
  - Define `LLMProvider`, `LLMRuntimeSettings`, `llm_settings_from_env`, and `build_llm_client`.
- Create: `cloud_incident_rca_agent/runtime/llm_invoke.py`
  - Define task-level invocation models and `invoke_llm_task`.
- Create: `cloud_incident_rca_agent/cli.py`
  - Add an async-aware CLI for invoking LLM tasks.
- Modify: `pyproject.toml`
  - Add a console script entrypoint.
- Test: `tests/test_runtime_config.py`
  - Cover environment parsing, fake default, OpenAI credential checks, and client construction.
- Test: `tests/test_llm_invoke.py`
  - Cover task-level fake invocation and unsupported task validation.
- Test: `tests/test_cli.py`
  - Cover CLI fake invocation and OpenAI env selection without live network calls.
- Modify: `tests/integration/test_live_clients.py`
  - Add one gated live CLI-adjacent smoke test for configured OpenAI runtime settings.

---

### Task 1: Add Runtime LLM Configuration

**Files:**
- Create: `cloud_incident_rca_agent/runtime/__init__.py`
- Create: `cloud_incident_rca_agent/runtime/config.py`
- Test: `tests/test_runtime_config.py`

- [ ] **Step 1: Write failing runtime config tests**

Create `tests/test_runtime_config.py`:

```python
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
```

- [ ] **Step 2: Run runtime config tests to verify they fail**

Run:

```bash
pytest tests/test_runtime_config.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'cloud_incident_rca_agent.runtime'`.

- [ ] **Step 3: Create runtime package exports**

Create `cloud_incident_rca_agent/runtime/__init__.py`:

```python
"""Runtime configuration and invocation helpers."""

from cloud_incident_rca_agent.runtime.config import (
    LLMProvider,
    LLMRuntimeSettings,
    build_llm_client,
    llm_settings_from_env,
)

__all__ = [
    "LLMProvider",
    "LLMRuntimeSettings",
    "build_llm_client",
    "llm_settings_from_env",
]
```

- [ ] **Step 4: Implement runtime config**

Create `cloud_incident_rca_agent/runtime/config.py`:

```python
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
```

- [ ] **Step 5: Run runtime config tests**

Run:

```bash
pytest tests/test_runtime_config.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit runtime config**

Run:

```bash
git add cloud_incident_rca_agent/runtime tests/test_runtime_config.py
git commit -m "Add runtime LLM configuration"
```

---

### Task 2: Add Task-Level LLM Invocation Service

**Files:**
- Modify: `cloud_incident_rca_agent/runtime/__init__.py`
- Create: `cloud_incident_rca_agent/runtime/llm_invoke.py`
- Test: `tests/test_llm_invoke.py`

- [ ] **Step 1: Write failing LLM invoke service tests**

Create `tests/test_llm_invoke.py`:

```python
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
```

- [ ] **Step 2: Run invoke service tests to verify they fail**

Run:

```bash
pytest tests/test_llm_invoke.py -v
```

Expected: fail with import errors for `LLMInvokeRequest`, `LLMTask`, and `invoke_llm_task`.

- [ ] **Step 3: Implement invocation service**

Create `cloud_incident_rca_agent/runtime/llm_invoke.py`:

```python
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
```

- [ ] **Step 4: Export invocation service**

Update `cloud_incident_rca_agent/runtime/__init__.py`:

```python
"""Runtime configuration and invocation helpers."""

from cloud_incident_rca_agent.runtime.config import (
    LLMProvider,
    LLMRuntimeSettings,
    build_llm_client,
    llm_settings_from_env,
)
from cloud_incident_rca_agent.runtime.llm_invoke import (
    LLMInvokeRequest,
    LLMInvokeResult,
    LLMTask,
    invoke_llm_task,
)

__all__ = [
    "LLMInvokeRequest",
    "LLMInvokeResult",
    "LLMProvider",
    "LLMRuntimeSettings",
    "LLMTask",
    "build_llm_client",
    "invoke_llm_task",
    "llm_settings_from_env",
]
```

- [ ] **Step 5: Run invoke service tests**

Run:

```bash
pytest tests/test_llm_invoke.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit invocation service**

Run:

```bash
git add cloud_incident_rca_agent/runtime tests/test_llm_invoke.py
git commit -m "Add task-level LLM invocation service"
```

---

### Task 3: Add CLI Entrypoint For LLM Invoke

**Files:**
- Create: `cloud_incident_rca_agent/cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
import json

from cloud_incident_rca_agent.cli import main


def test_cli_invokes_fake_normalize_and_prints_json(capsys) -> None:
    exit_code = main(
        [
            "llm-invoke",
            "--provider",
            "fake",
            "--task",
            "normalize",
            "checkout API returns 500",
        ]
    )

    assert exit_code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["task"] == "normalize"
    assert output["payload"]["normalized_summary"] == "checkout API returns 500"


def test_cli_returns_error_for_openai_without_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    exit_code = main(
        [
            "llm-invoke",
            "--provider",
            "openai",
            "--task",
            "normalize",
            "checkout API returns 500",
        ]
    )

    assert exit_code == 2
    assert "OPENAI_API_KEY is required" in capsys.readouterr().err
```

- [ ] **Step 2: Run CLI tests to verify they fail**

Run:

```bash
pytest tests/test_cli.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'cloud_incident_rca_agent.cli'`.

- [ ] **Step 3: Implement CLI**

Create `cloud_incident_rca_agent/cli.py`:

```python
"""Command line interface for cloud incident RCA helpers."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

from cloud_incident_rca_agent.runtime import (
    LLMInvokeRequest,
    LLMProvider,
    LLMRuntimeSettings,
    LLMTask,
    build_llm_client,
    invoke_llm_task,
    llm_settings_from_env,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloud-incident-rca")
    subparsers = parser.add_subparsers(dest="command", required=True)

    invoke = subparsers.add_parser("llm-invoke")
    invoke.add_argument("--provider", choices=[item.value for item in LLMProvider], default=None)
    invoke.add_argument("--model", default=None)
    invoke.add_argument("--task", choices=[item.value for item in LLMTask], required=True)
    invoke.add_argument("raw_description")
    return parser


async def _run_llm_invoke(args: argparse.Namespace) -> int:
    base_settings = llm_settings_from_env()
    settings = LLMRuntimeSettings(
        provider=LLMProvider(args.provider) if args.provider else base_settings.provider,
        openai_api_key=base_settings.openai_api_key,
        openai_model=args.model or base_settings.openai_model,
    )
    client = build_llm_client(settings)
    result = await invoke_llm_task(
        client,
        LLMInvokeRequest(
            task=LLMTask(args.task),
            raw_description=args.raw_description,
        ),
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "llm-invoke":
            return asyncio.run(_run_llm_invoke(args))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add console script**

Modify `pyproject.toml` by adding:

```toml
[project.scripts]
cloud-incident-rca = "cloud_incident_rca_agent.cli:main"
```

- [ ] **Step 5: Run CLI tests**

Run:

```bash
pytest tests/test_cli.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run CLI manually with fake provider**

Run:

```bash
python -m cloud_incident_rca_agent.cli llm-invoke --provider fake --task normalize "checkout API returns 500"
```

Expected: exit code `0` and JSON containing:

```json
{
  "task": "normalize",
  "payload": {
    "raw_description": "checkout API returns 500",
    "normalized_summary": "checkout API returns 500"
  }
}
```

The output will include additional incident fields and generated IDs.

- [ ] **Step 7: Commit CLI**

Run:

```bash
git add cloud_incident_rca_agent/cli.py pyproject.toml tests/test_cli.py
git commit -m "Add CLI for LLM invocation"
```

---

### Task 4: Add Gated Runtime Integration Coverage

**Files:**
- Modify: `tests/integration/test_live_clients.py`

- [ ] **Step 1: Add failing integration test for runtime settings**

Append this test to `tests/integration/test_live_clients.py`:

```python
from cloud_incident_rca_agent.runtime import (
    LLMProvider,
    build_llm_client,
    llm_settings_from_env,
)


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY is required for live OpenAI runtime smoke test",
)
def test_live_openai_runtime_settings_build_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUD_RCA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))

    settings = llm_settings_from_env()
    client = build_llm_client(settings)

    assert settings.provider == LLMProvider.OPENAI
    assert client.__class__.__name__ == "OpenAILLMClient"
```

- [ ] **Step 2: Run integration tests without env**

Run:

```bash
pytest tests/integration/test_live_clients.py -v
```

Expected: integration tests are skipped unless the required environment variables are set.

- [ ] **Step 3: Run default test suite**

Run:

```bash
pytest -v
```

Expected: all default tests pass; live integration tests remain skipped unless configured.

- [ ] **Step 4: Commit integration coverage**

Run:

```bash
git add tests/integration/test_live_clients.py
git commit -m "Add runtime LLM integration smoke coverage"
```

---

### Task 5: Final Verification And Push

**Files:**
- Inspect: all files touched by this plan.

- [ ] **Step 1: Run full default tests**

Run:

```bash
pytest -v
```

Expected: all default tests pass, with live integration tests skipped unless configured.

- [ ] **Step 2: Check public imports**

Run:

```bash
python - <<'PY'
from cloud_incident_rca_agent.runtime import (
    LLMInvokeRequest,
    LLMInvokeResult,
    LLMProvider,
    LLMRuntimeSettings,
    LLMTask,
    build_llm_client,
    invoke_llm_task,
    llm_settings_from_env,
)

print(LLMInvokeRequest.__name__, LLMInvokeResult.__name__)
print(LLMProvider.FAKE, LLMProvider.OPENAI)
print(LLMRuntimeSettings.__name__, LLMTask.NORMALIZE)
print(build_llm_client.__name__, invoke_llm_task.__name__, llm_settings_from_env.__name__)
PY
```

Expected output includes:

```text
LLMInvokeRequest LLMInvokeResult
fake openai
LLMRuntimeSettings normalize
build_llm_client invoke_llm_task llm_settings_from_env
```

- [ ] **Step 3: Run fake CLI smoke test**

Run:

```bash
python -m cloud_incident_rca_agent.cli llm-invoke --provider fake --task plan "checkout API returns 500"
```

Expected: exit code `0` and JSON containing `"task": "plan"` plus a payload with `"tool_intents"`.

- [ ] **Step 4: Check worktree**

Run:

```bash
git status --short
```

Expected: only user-owned unrelated files may remain. Do not revert unrelated changes such as documentation moves or generated egg-info unless explicitly requested.

- [ ] **Step 5: Push branch**

Run:

```bash
git push
```

Expected: `feature/cloud-incident-rca-agent` updates on `origin`.

---

## Self-Review

Spec coverage:

- The existing LLM boundary remains provider-neutral.
- OpenAI is selected only through explicit runtime settings or environment variables.
- Fake remains the default path for local and test usage.
- CLI invocation supports practical task-level API use without requiring MCP connectors.
- Live OpenAI remains gated by environment and optional dependency installation.

Placeholder scan:

- No step uses placeholder language or unspecified "add tests" language.
- Every code-writing step includes concrete code and exact file paths.
- Every verification step includes exact commands and expected outcomes.

Type consistency:

- `LLMProvider`, `LLMRuntimeSettings`, `LLMTask`, `LLMInvokeRequest`, and `LLMInvokeResult` are exported from `cloud_incident_rca_agent.runtime`.
- The CLI uses the same `LLMTask` values as the invocation service.
- `build_llm_client` returns the existing `LLMClient` protocol implementations without changing orchestrator code.
