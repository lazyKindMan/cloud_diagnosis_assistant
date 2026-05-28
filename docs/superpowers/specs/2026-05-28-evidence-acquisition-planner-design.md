# Evidence Acquisition Planner Design

Date: 2026-05-28

## Context

The project already has a bounded RCA orchestrator, strict Pydantic domain models,
provider-neutral LLM clients, connector boundaries for `cls-log-mcp`, Chrome, and
MySQL, a fake-backed orchestrator happy path, human review flow, and live OpenAI
structured output support.

The remaining gap is evidence acquisition reasoning. The current planner can
produce generic `ToolIntent` objects, but it does not explicitly decide why a
specific log query, code read, or SQL query is needed, how that evidence maps to
a hypothesis, or how the investigation should safely continue when a plan fails
to locate a root cause.

## Goal

Add a unified evidence acquisition planning layer that can plan and execute
bounded evidence collection across logs, local code, and SQL validation, with
controlled replanning loops and explicit stop reasons.

The first implementation slice is intentionally constrained:

- memory is scoped to one RCA investigation session and is persisted only so the
  same investigation can resume, compact context, and avoid repeated work;
- local code inspection executes against the current workspace;
- SQL is generated, validated, and emitted as dry-run evidence, but not executed
  against a real database;
- local log file filtering can execute when files are available;
- `cls-log-mcp` and Chrome MCP remain planned integration routes, but require
  explicit configured clients before live execution;
- the orchestrator may replan, but only within fixed round and request budgets.

## Non-Goals

- Do not connect to a real database in this slice.
- Do not automate Chrome MCP navigation or cloud console interaction in this
  slice.
- Do not execute write operations or remediation.
- Do not let the LLM read arbitrary files or issue arbitrary SQL.
- Do not build cross-incident long-term learning or vector memory in this slice.
- Do not replace the plain Python orchestrator with an agent framework.

## Current Gaps

### Log Evidence

The agent does not yet decide whether a log investigation should use
`cls-log-mcp`, a Chrome console page, or a local log file. It also lacks required
query constraints such as time window, service name, trace id, route, error code,
or bounded keywords.

### Code Evidence

The agent has no first-class code inspection plan. It cannot describe which
search terms to use, which local paths are allowed, why specific files are
relevant, or how code evidence supports or contradicts a hypothesis.

### SQL Evidence

The MySQL connector has a read-only guard, but there is no structured process
for deriving a query from a hypothesis, validating table and field assumptions,
or explaining how a query result would affect root-cause confidence.

### Replanning

The orchestrator can block or summarize, but it does not yet loop through a new
evidence plan when the current evidence is insufficient. It also lacks explicit
replan round limits, duplicate request prevention, and structured stop reasons.

### Session And Memory

The agent does not yet have a durable single-investigation session. It cannot
resume an interrupted RCA, compact prior context before the next LLM call, or
record request fingerprints across rounds to prevent repeated log, code, and SQL
work.

## Architecture

Add an evidence acquisition layer between the existing `Planner` and connector
execution. The new layer owns evidence-specific planning, request policy, local
execution, and replanning decisions. The orchestrator remains responsible for
state transitions and budget enforcement.

Core units:

- `EvidencePlanner`: asks the LLM for a structured `EvidenceAcquisitionPlan`
  based on incident state, hypotheses, prior evidence, request results, and
  remaining budgets.
- `EvidenceAcquisitionPolicy`: validates planned requests and decides whether
  to continue, replan, summarize, block, or require human review.
- `EvidenceExecutor`: dispatches approved evidence requests to local log,
  local code, SQL dry-run, or existing MCP connector routes.
- `LocalCodeInspector`: searches and reads bounded snippets from the workspace.
- `LocalLogInspector`: filters allowed local log files by query constraints.
- `SqlDryRunValidator`: validates generated SQL and emits safe dry-run evidence.
- `AgentSessionManager`: creates, checkpoints, loads, and resumes one RCA
  session using local file storage in the first slice.
- `InvestigationMemory`: stores working memory, round history, stable facts, and
  request fingerprints for one RCA session.
- `ContextBuilder`: compacts session memory into a bounded prompt context for
  LLM planning, hypothesis updates, and report generation.
- Playbook prompts: guide LLM planning for log acquisition, code inspection, SQL
  validation, and replanning without owning execution flow.

## Domain Model Additions

### EvidenceAcquisitionPlan

Represents one bounded investigation round.

Fields:

- `plan_id`: generated id.
- `round_number`: one-based round number.
- `objective`: the specific evidence objective for this round.
- `requests`: non-empty list of evidence requests.
- `max_requests`: maximum requests to execute in this round.
- `stop_conditions`: textual conditions under which this round should stop.
- `replan_reason`: why this round exists; `None` on the initial round.

### EvidenceRequest

Shared base contract for evidence requests.

Fields:

- `request_id`: generated id.
- `kind`: `log`, `code`, or `sql`.
- `hypothesis_ref`: hypothesis id, title, or provisional hypothesis label.
- `question`: the concrete question this request answers.
- `expected_signal`: the observation expected to support or contradict the
  hypothesis.
- `risk_level`: low, medium, or high.
- `requires_human_review`: whether execution must pause before running.

### LogEvidenceRequest

Plans log evidence retrieval.

Fields:

- `route`: `cls_mcp`, `chrome_mcp`, or `local_file`.
- `service_name`: service or application component, when known.
- `time_window`: bounded time window.
- `keywords`: query terms such as error code, route, exception, trace id, or
  symptom.
- `trace_id`: optional trace id.
- `query`: concrete log query when available.
- `aggregation`: optional grouping request such as error signature, route, host,
  or trace.
- `chrome_page_hint`: page type or URL hint when Chrome is needed to discover
  CLS query context.
- `local_path_hint`: local log path or directory hint when using local files.

### CodeEvidenceRequest

Plans local code inspection.

Fields:

- `search_terms`: keywords or symbols to search with `rg`.
- `path_allowlist`: workspace-relative directories allowed for this request.
- `file_globs`: allowed source file patterns.
- `max_files`: maximum files to read.
- `max_bytes_per_file`: maximum bytes per file snippet budget.
- `read_strategy`: `search_first` or `direct_path`.
- `why_these_files`: rationale for the selected search scope.
- `expected_signal`: code-level observation expected from the search.

### SqlEvidenceRequest

Plans a SQL validation query without executing it in the first slice.

Fields:

- `schema_context`: known table and field summary.
- `hypothesis_ref`: hypothesis being verified.
- `validation_purpose`: what the query should prove or disprove.
- `tables`: tables referenced by the query.
- `sql`: generated read-only SQL statement.
- `parameters`: safe parameter values or named bind parameters.
- `expected_result_shape`: `single_row`, `rows`, `count`, or `aggregate`.
- `interpretation_rule`: how results affect the hypothesis.
- `safety_notes`: explanation of why the query is bounded and safe.

### EvidenceRequestResult

Records execution or policy outcome for one request.

Fields:

- `request_id`: originating request id.
- `success`: whether evidence was produced.
- `evidence`: normalized evidence list.
- `status`: `executed`, `skipped`, `policy_blocked`, `requires_review`, or
  `failed`.
- `message`: human-readable outcome.
- `connector_error`: optional structured connector error.

### ReplanDecision

Records the policy decision after a round.

Fields:

- `action`: `replan`, `summarize`, `block`, or `human_review`.
- `reason`: structured stop or continuation reason.
- `missing_evidence`: evidence still needed before confidence can improve.
- `remaining_rounds`: remaining replan budget.

### StopReason

Enum values:

- `root_cause_confident`
- `plan_round_budget_exhausted`
- `tool_budget_exhausted`
- `no_new_evidence`
- `requires_human_review`
- `policy_blocked`
- `repeated_failed_requests`

### AgentSession

Represents one recoverable RCA investigation.

Fields:

- `session_id`: generated id.
- `created_at`: session creation timestamp.
- `updated_at`: last checkpoint timestamp.
- `raw_incident`: original incident text.
- `current_state`: current investigation state.
- `status`: `running`, `pending_review`, `done`, `blocked`, or `failed`.
- `round_number`: current evidence planning round.
- `budgets`: configured and remaining investigation budgets.
- `memory`: single-session investigation memory.
- `checkpoint_version`: monotonically increasing checkpoint version.

### InvestigationMemory

Stores memory for a single RCA session only.

Fields:

- `working_summary`: compact summary of the current investigation.
- `stable_facts`: service names, routes, table names, trace ids, time windows,
  schema context, and other facts that have survived evidence review.
- `rounds`: ordered summaries of each planning and evidence collection round.
- `attempted_request_fingerprints`: normalized fingerprints for log, code, and
  SQL requests already attempted.
- `failed_request_fingerprints`: fingerprints of failed or policy-blocked
  requests.
- `open_questions`: unresolved questions that justify replanning.
- `context_token_budget`: maximum approximate context size for the next LLM
  planning prompt.

### RoundMemory

Records what happened in one planning round.

Fields:

- `round_number`: round index.
- `plan_id`: evidence acquisition plan id.
- `objective`: round objective.
- `request_results`: normalized request outcomes.
- `new_evidence_ids`: evidence produced by the round.
- `hypothesis_summary`: compact hypothesis changes after the round.
- `stop_reason`: reason this round stopped or continued.

### ContextPacket

Represents the bounded context sent to the LLM.

Fields:

- `incident_summary`: compact incident description.
- `current_hypotheses`: highest-value hypotheses and confidence scores.
- `recent_evidence_summary`: evidence from recent rounds.
- `stable_facts`: durable facts useful for planning.
- `open_questions`: missing evidence to target next.
- `attempted_requests`: compact list of prior request fingerprints.
- `remaining_budgets`: plan rounds, tool calls, code bytes, SQL statements, and
  request limits.

## Evidence Planning Rules

Every evidence request must answer a concrete question and name the hypothesis or
provisional hypothesis it is meant to support or contradict. The planner may not
produce broad discovery requests such as "search all logs" or "read the codebase".

Requests are prioritized as follows:

1. Use direct evidence from the incident first: trace id, service, route, error
   code, time window, order id, user id, deployment id.
2. If log context is missing, plan a Chrome or local-file discovery request only
   when an allowed page or path hint exists.
3. Use code inspection to identify execution path, table names, config, error
   handling, and likely persistence operations.
4. Generate SQL only when schema context is sufficient; otherwise request more
   code evidence or block with missing context.
5. Avoid repeating equivalent requests across rounds.

## Replanning Loop

The orchestrator should support bounded evidence planning rounds:

1. `PLAN`: generate `EvidenceAcquisitionPlan(round_number=N)`.
2. `COLLECT_EVIDENCE`: validate and execute approved requests.
3. `UPDATE_HYPOTHESES`: update hypotheses using newly collected evidence.
4. `VERIFY`: ask `EvidenceAcquisitionPolicy` whether to summarize, replan,
   block, or request human review.
5. If action is `replan`, transition back to `PLAN` with incremented
   `round_number`.

Default budgets:

- `max_plan_rounds`: 3.
- `max_requests_per_round`: 3.
- `max_total_tool_calls`: keep compatible with `InvestigationState.max_tool_calls`.
- `max_code_files_per_round`: 5.
- `max_code_bytes_per_file`: 20000.
- `max_sql_statements_per_round`: 3.
- `min_confidence_to_summarize`: 0.75.
- `forbid_duplicate_requests`: enabled.

The loop stops when confidence is high enough, budgets are exhausted, no new
evidence was produced, a policy block occurs, repeated failures occur, or human
review is required.

Every state transition and evidence round should checkpoint the current
`AgentSession`. A resumed session must continue from the saved state, preserve
request fingerprints, and retain remaining budgets.

## Agent Session And Memory Management

The first slice should feel agent-like without becoming an unconstrained agent.
Memory is scoped to one RCA investigation session. It exists to resume work,
compress prompt context, explain progress, and prevent repeated work.

### Session Storage

Use a local JSON session store in the first slice.

Responsibilities:

- create a new session from raw incident text;
- checkpoint after each state transition and completed evidence round;
- load a session by `session_id`;
- resume from `pending_review`, `running`, or interrupted states;
- reject resume for incompatible `checkpoint_version` values with a clear error.

No external database is required for session storage in this phase.

### Memory Layers

Working memory contains the current incident, active plan, hypotheses, evidence,
request results, open questions, and remaining budgets.

Round memory contains compact per-round history: what was planned, what ran,
what produced evidence, what failed, and why the agent continued or stopped.

Stable facts contain durable values discovered during the investigation, such as
service name, API route, trace id, project/logstore hints, table names, field
names, schema context, and code entrypoints.

Prompt context memory is a compact `ContextPacket` built from the larger session
state. The LLM should receive the packet instead of the full raw history.

### Context Compaction

`ContextBuilder` must keep LLM inputs bounded.

It should include:

- incident summary;
- top hypotheses and confidence;
- recent evidence summaries;
- stable facts relevant to the next round;
- unresolved questions;
- attempted request fingerprints;
- remaining budgets.

It should exclude:

- full file contents;
- full log files;
- repeated historical evidence;
- sensitive raw payloads;
- unrelated execution log noise.

When context exceeds the configured approximate budget, older round details are
summarized into `working_summary` while preserving stable facts, open questions,
and request fingerprints.

### Request Fingerprints

Each request should have a deterministic fingerprint used for duplicate
prevention:

- log fingerprint: route, service, time window, trace id, normalized keywords,
  query, and local path hint;
- code fingerprint: normalized search terms, path allowlist, file globs, and
  selected file paths;
- SQL fingerprint: normalized SQL, tables, validation purpose, and parameter
  names.

Replanning must not repeat an equivalent fingerprint unless the new request
explains the new evidence or changed constraint that makes repetition useful.

### Agent-Facing Operations

The runtime surface should eventually expose operations that make the system
feel like a controlled agent:

- start an RCA session;
- inspect current session status;
- resume a paused session;
- approve or reject a pending review;
- show memory summary and attempted requests;
- export final RCA report and investigation trace.

These operations still call code-controlled state transitions and executors.
They do not allow the LLM to call tools directly.

## Log Evidence Strategy

### cls_mcp Route

Use when the incident or prior evidence provides enough query context.

Required constraints:

- bounded time window;
- at least one narrowing condition such as service, trace id, route, error code,
  or specific keyword;
- explicit query purpose and expected signal.

The route uses the existing `ClsLogMCPConnector` when a real MCP client is
configured. Without a configured client, execution returns a clear permanent
connector error rather than silently succeeding.

### chrome_mcp Route

Use when the agent needs read-only cloud console context before a CLS query can
be formed.

Allowed page types:

- `cls_query`
- `alarm`
- `deployment`
- `trace`
- `metrics`

The plan must specify page type, URL hint when available, fields to inspect, and
expected signal. First-slice execution does not automate Chrome MCP; it records a
planned or skipped result unless a configured connector is provided.

### local_file Route

Use when a local log file path or allowed log directory is available.

Execution constraints:

- read only workspace-allowed paths;
- do not read `.env`, key, secret, credential, or hidden files;
- filter by keywords, trace id, and time window when present;
- cap total bytes and returned matching lines;
- return summaries and snippets, not whole files.

## Code Evidence Strategy

Code inspection uses a search-first workflow by default.

1. Search with `rg` using planned `search_terms`.
2. Exclude `.git`, `.venv`, `__pycache__`, egg-info, lock files, build output,
   hidden files, and credential-like files.
3. Rank candidate files by path and match relevance.
4. Read bounded snippets from at most `max_files`.
5. Emit normalized evidence with path, line numbers, matched snippets, and a
   concise summary.

Path priority:

1. route, controller, handler, API entrypoint;
2. service, use case, domain workflow;
3. repository, DAO, model, persistence;
4. config and dependency wiring;
5. middleware, exception handling, retries;
6. tests that clarify expected behavior.

The LLM proposes search scope and explains why it matters. Code owns path
allowlisting, file exclusions, byte limits, and duplicate read prevention.

## SQL Evidence Strategy

The first slice validates SQL but does not execute it against a database.

SQL generation requirements:

- SQL must be tied to a hypothesis and validation purpose.
- SQL must use known schema context. If table or field context is missing, the
  planner must request code evidence or report missing context.
- Non-aggregate queries must include `WHERE` and `LIMIT`.
- Queries must define an interpretation rule.

Policy validator rules:

- allow only one `SELECT` or `WITH ... SELECT` statement;
- reject multi-statement SQL;
- reject mutation, DDL, transaction, stored procedure, and session-control
  keywords;
- reject `SELECT *`;
- reject non-aggregate queries without `LIMIT`;
- reject broad table scans without a narrowing `WHERE`;
- reject direct selection of sensitive fields such as password, token, secret,
  access key, private key, and credential values.

When validation passes, the dry-run connector emits evidence stating that the SQL
is safe and ready for future MySQL MCP execution, with structured data containing
SQL, tables, purpose, and interpretation rule.

## Human Review

Human review is required when:

- a request touches sensitive data;
- SQL references potentially sensitive fields;
- Chrome page inspection has no allowed URL hint;
- a local path is outside the allowlist;
- a replan proposes broader scope than prior rounds;
- policy cannot determine whether a request is safe.

Review decisions reuse the existing `HumanReviewRequest` and
`HumanReviewDecision` models.

## Prompt Assets

Add markdown playbooks under a project prompt or skills directory:

- `evidence_planning.md`: how to choose log, code, or SQL evidence requests.
- `log_acquisition.md`: how to form bounded CLS, Chrome, or local log requests.
- `code_inspection.md`: how to search for API entrypoints, persistence paths,
  config, and error handling.
- `sql_validation.md`: how to generate bounded read-only verification queries.
- `replanning.md`: how to explain missing evidence and avoid repeated requests.

These files guide LLM planning. They do not own execution flow, state
transitions, or safety enforcement.

## Testing Strategy

### Domain Tests

Verify evidence plan schemas, request variants, strict field validation, stop
reasons, and request result states.

### Policy Tests

Verify max round enforcement, per-round request limits, confidence threshold,
duplicate request blocking, no-new-evidence handling, and human review triggers.

### Session And Memory Tests

Verify session creation, checkpoint persistence, resume behavior, checkpoint
version validation, context compaction, stable fact retention, open question
retention, and duplicate request fingerprint blocking across replans.

### Local Code Tests

Verify search term execution, path allowlist enforcement, secret file exclusion,
file count limits, byte limits, snippet output, and duplicate read prevention.

### Local Log Tests

Verify keyword filtering, trace id filtering, time window handling when present,
path allowlist enforcement, and returned line limits.

### SQL Tests

Verify safe query acceptance and rejection of mutation, multi-statement SQL,
`SELECT *`, missing `LIMIT`, broad scans, and sensitive fields.

### Orchestrator Tests

Cover:

- one-round success;
- two-round replan after insufficient evidence;
- max rounds exhausted;
- duplicate request policy block;
- SQL dry-run evidence contributing to hypotheses;
- code evidence contributing to hypotheses;
- human review pause for risky request.

### Scenario Replay Tests

Add at least three fixture-backed scenarios:

- API 500 requiring code entrypoint inspection.
- Failed persistence requiring SQL dry-run validation.
- Missing log context requiring replan after local log evidence is insufficient.

## Phase Scope

### Phase 1: Evidence Planner Foundation

Implement evidence plan domain models, policy decisions, SQL validator, local
code inspector, local log inspector, local JSON session storage, single-session
memory, context compaction, and fake-backed orchestrator replan flow.

### Phase 2: Runtime Surface

Expose evidence planning and RCA run commands through CLI, including JSON output
for session id, plan rounds, request results, evidence, memory summary, stop
reason, and report.

### Phase 3: Live Integration

Add configured MCP clients for `cls-log-mcp`, Chrome MCP, and MySQL MCP. Keep all
live tests gated and default test suite offline.

## Definition Of Done

This design is implemented when:

- evidence acquisition plans can include log, code, and SQL requests;
- code requests can read bounded local snippets from the workspace;
- SQL requests are generated, validated, and emitted as dry-run evidence;
- log requests can filter local files and represent `cls-log-mcp` or Chrome MCP
  plans;
- the orchestrator can replan up to a configured max round count;
- a single RCA session can checkpoint, resume, compact memory, and prevent
  duplicate requests across rounds;
- stop reasons are explicit in the run result;
- policy prevents broad file reads, broad log searches, unsafe SQL, duplicate
  requests, and unbounded loops;
- default tests pass without live OpenAI, Chrome, CLS, or MySQL services.
