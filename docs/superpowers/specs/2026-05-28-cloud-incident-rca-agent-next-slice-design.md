# Cloud Incident RCA Agent Next Slice Design

Date: 2026-05-28

## Context

The project already has the first implementation slice:

- Strict Pydantic domain models for incidents, evidence, hypotheses, investigation state, and RCA reports.
- A plain Python investigation state machine.
- Tests for core model validation and nominal state transitions.
- A seed product spec in `doc/superpower_spec_cloud_incident_rca_agent.md`.

This design covers the next implementation slice only. It should add a thin, runnable vertical workflow around the existing state and model primitives.

## Goal

Build a minimal end-to-end orchestrator that can drive an incident investigation through intake, classification, planning, human review, evidence collection, hypothesis update, verification, summarization, and completion.

The slice must support real integration boundaries for:

- A provider-neutral `LLMClient`, with OpenAI implemented first.
- MCP connectors for `cls-log-mcp`, Chrome, and MySQL.

The default test suite must use fakes and must not require live LLM credentials or running MCP servers. Live integration tests are optional and gated by environment or explicit configuration.

## Non-Goals

- Do not build remediation or mutation workflows.
- Do not implement a custom log MCP.
- Do not require live OpenAI or MCP services for normal `pytest`.
- Do not make Chrome or MySQL connectors capable of changing production state.
- Do not create a rich autonomous agent beyond the bounded state machine.

## Architecture

The next slice will add a thin vertical workflow around the existing `InvestigationState` and `InvestigationStateMachine`.

Core units:

- `CloudIncidentRCAOrchestrator`: owns the lifecycle loop and state transitions. It does not know provider-specific LLM or MCP details.
- `Planner`: produces a bounded `InvestigationPlan` from the incident and current state.
- `ToolRouter`: maps planned tool intents to connector calls.
- MCP connector interfaces: normalize real `cls-log-mcp`, Chrome, and MySQL observations into `Evidence`.
- `LLMClient`: provider-neutral contract, with OpenAI implemented first.
- `HypothesisManager`: updates candidate hypotheses from evidence and LLM output.
- `ReportBuilder`: turns final state into an `RCAReport`.

The orchestrator should remain deliberately simple: run a phase, validate the transition, append execution logs, check budgets, and apply stopping conditions. Reasoning belongs behind planner, hypothesis, and report components. External calls stay behind connector and LLM boundaries.

## State Machine Changes

Add a new state:

- `HUMAN_REVIEW`

`HUMAN_REVIEW` is a first-class lifecycle state. The orchestrator enters it whenever the next action has meaningful ambiguity, operational risk, safety impact, sensitive data exposure, broad scope expansion, or an important investigation choice.

Required transitions:

- `PLAN -> HUMAN_REVIEW -> COLLECT_EVIDENCE` when a plan needs approval and is approved.
- `PLAN -> HUMAN_REVIEW -> PLAN` when the plan is rejected and needs revision.
- `VERIFY -> HUMAN_REVIEW -> COLLECT_EVIDENCE` when the next evidence step needs approval.
- `VERIFY -> HUMAN_REVIEW -> SUMMARIZE` when the human chooses to stop and summarize.
- `SUMMARIZE -> HUMAN_REVIEW -> DONE` when the final report needs acceptance.
- `HUMAN_REVIEW -> BLOCKED` when approval is required but unavailable.

Existing transitions that do not require review remain valid. The orchestrator must never auto-continue past a required review point without an explicit decision object.

## Data Flow

The orchestrator flow should be:

1. Start with `Incident(raw_description=...)` and create `InvestigationState`.
2. `INTAKE`: call `LLMClient` to normalize summary, service, environment, timeframe, extracted signals, and missing context.
3. `CLASSIFY`: call `LLMClient` to assign issue category and suspicion areas.
4. `PLAN`: call `Planner` to produce ordered tool intents, max tool calls, stopping criteria, and any required human approval points.
5. `HUMAN_REVIEW`: pause when approval is required for ambiguity, safety, sensitive data, risky inspection, broad scope expansion, or an important investigation choice.
6. `COLLECT_EVIDENCE`: after approval, route each pending intent to `cls-log-mcp`, Chrome, or MySQL connectors. Each connector returns normalized `Evidence`.
7. `UPDATE_HYPOTHESES`: call `HypothesisManager` to create or update hypotheses using accumulated evidence.
8. `VERIFY`: decide whether confidence is sufficient, budget is exhausted, context is missing, human review is needed, or more evidence should be collected.
9. `SUMMARIZE`: call `ReportBuilder` to produce structured `RCAReport`, optionally entering `HUMAN_REVIEW` first for low-confidence or safety-sensitive conclusions.
10. `DONE`, `BLOCKED`, or `FAILED`: return final state plus report or failure reason.

Tool calls increment `tool_call_count` only when an actual connector invocation is attempted.

## New Domain Models

Add small explicit models for orchestration contracts:

- `InvestigationPlan`
  - ordered tool intents
  - max tool calls for the plan
  - stopping criteria
  - review requirements
- `ToolIntent`
  - target source: `cls-log-mcp`, Chrome, MySQL, or other
  - tool name or action name
  - structured parameters
  - purpose
  - sensitivity flag
  - whether human review is required
- `ToolResult`
  - originating intent id
  - success or failure
  - normalized evidence list
  - connector error if any
- `ConnectorError`
  - error category
  - message
  - retryable flag
  - raw metadata safe for logs
- `HumanReviewRequest`
  - reason
  - proposed action
  - risk level
  - alternatives
  - recommended option
  - affected tool intents
- `HumanReviewDecision`
  - approved, rejected, or approved with modifications
  - reviewer note
  - modified tool intents when applicable

These models should follow the existing strict Pydantic style and reject unknown fields.

## Connector Design

Define a shared connector protocol with one responsibility: execute a typed tool intent and return normalized evidence or a classified connector error.

Connector expectations:

- `cls-log-mcp` connector calls existing log MCP tools for log search, clustering, and report synthesis. It is the only supported log path.
- Chrome connector performs inspection only. It must not mutate cloud console state.
- MySQL connector accepts only read-only queries. It must reject write, DDL, transaction-control, and ambiguous multi-statement inputs before execution.
- All connectors return `Evidence` objects instead of leaking provider-specific payloads into the orchestrator.
- Raw payloads may be stored in `structured_data` only when safe and useful. Sensitive data must be marked with `sensitive=True`.

## LLM Design

Use a provider-neutral `LLMClient` boundary so orchestration code does not depend on one SDK. Implement OpenAI first behind that boundary.

The client should support structured tasks for:

- incident intake normalization
- classification
- planning assistance
- hypothesis update
- report generation

LLM output must be schema validated. If the model returns invalid structured output, classify it as a semantic failure and either retry with a repair prompt or block with a clear reason.

## Error Handling

Classify failures into explicit categories:

- `transient`: timeout, temporary MCP failure, retryable provider error.
- `permanent`: unsupported tool, missing credentials, unavailable MCP server, invalid configuration.
- `semantic`: connector returned data but it cannot be normalized into `Evidence`, LLM output failed schema validation, or the result does not answer the intended question.
- `policy`: action requires `HUMAN_REVIEW`, exceeds budget, requests mutation, or would access data outside approved scope.

Retry only transient failures, with a small fixed retry count. Permanent, repeated semantic, and policy failures should move the investigation to `BLOCKED` unless the planner can produce a safe alternate route.

## Safety Rules

- All MCP connectors are read-only in this slice.
- MySQL connector allows only read statements.
- Browser and Chrome connector behavior is inspection-only.
- Any planned action with sensitive data, expanded scope, unclear target, or material decision impact must create a `HumanReviewRequest`.
- Evidence marked `sensitive=True` should be summarized in reports without leaking raw payloads.
- Tool budget and approved scope are enforced in code, not left to prompts.

## Testing

Normal test suite:

- Unit tests for state-machine transitions, including `HUMAN_REVIEW`.
- Unit tests for `InvestigationPlan`, `ToolIntent`, `HumanReviewRequest`, and `HumanReviewDecision` validation.
- Orchestrator tests using fake `LLMClient` and fake MCP connectors to prove:
  - happy path reaches `DONE`
  - plan requiring approval pauses at `HUMAN_REVIEW`
  - approval continues to evidence collection
  - rejection returns to `PLAN`
  - budget exhaustion moves to `BLOCKED` or `SUMMARIZE` based on confidence
  - connector failures are classified correctly
- Connector unit tests for SQL read-only validation and evidence normalization contracts.
- Report builder tests that verify evidence-backed output and sensitive evidence redaction behavior.

Optional live integration tests:

- Gated by env or config so `pytest` does not require credentials or running MCP servers.
- Smoke test OpenAI-backed `LLMClient`.
- Smoke test `cls-log-mcp`, Chrome, and MySQL connectors individually.
- One manual or gated end-to-end test can run the thin orchestrator against configured live dependencies.

No live OpenAI or MCP dependency should be required for the default test suite.

## Definition Of Done

This next slice is complete when:

- `HUMAN_REVIEW` exists in the state machine with tests for approved, rejected, and blocked paths.
- A thin orchestrator can run a fake-backed happy path from raw incident text to `DONE`.
- A fake-backed review path pauses at `HUMAN_REVIEW` and resumes only after a `HumanReviewDecision`.
- Provider-neutral LLM and MCP connector interfaces exist.
- OpenAI LLM and real MCP connector implementations are present behind gated configuration.
- Default tests pass without live credentials or services.
- Optional integration tests are clearly marked or skipped unless configured.
