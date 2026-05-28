# Superpower Spec: Cloud Incident RCA Agent (Constrained, cls-log-mcp)

## 0. Mission

Build a **controlled incident diagnosis agent** for cloud application troubleshooting.

The agent's main job is to:
1. parse an incident description
2. create a bounded investigation plan
3. call MCP tools to collect evidence
4. maintain investigation state
5. update and verify hypotheses
6. output an evidence-backed RCA report

> Note: This is a **stateful diagnosis orchestrator**, not an unconstrained autonomous agent.

---

## 1. Technology Stack

- **Python 3.12+**
- **Original Python orchestrator** (asyncio + explicit state machine)
- **Pydantic v2** (typed models: Incident, Evidence, Hypothesis, RCAReport)
- **FastMCP** (only for MCP client integration if needed)
- **Existing MCPs**:
  - `cls-log-mcp` (log filtering, cleaning, aggregation, redaction)
  - Chrome MCP (browser inspection / cloud console)
  - MySQL MCP (read-only queries / state validation)
- **LLM integration**: LiteLLM or OpenAI / Anthropic Python SDK
- **Logging & observability**: structlog or standard logging
- **Testing**: pytest
- **Package management**: poetry / pip + pyproject.toml

> **Do not use LangChain or LangGraph in v1.** Orchestrator should remain plain Python.

---

## 2. Build Philosophy

1. **Code owns orchestration**:
   - State transitions
   - Tool call sequence & budget
   - Evidence accumulation
   - Policies & stopping conditions
   - RCA report construction

2. **Skills guide reasoning**:
   - Playbooks / prompts / heuristics
   - Do not contain execution flow or state control

3. **MCP provides capability, not orchestration**:
   - Tools / resources / prompts
   - Orchestrator decides sequence and stopping

---

## 3. Scope

### 3.1 In-Scope
- API 500 errors / failed persistence
- Timeout or failed writes
- Data inconsistency
- Cloud console / browser inspection
- Logs via `cls-log-mcp`
- Read-only MySQL verification
- Evidence-backed RCA output

### 3.2 Out-of-Scope
- Any production mutation (DB or cloud)
- Full autonomous remediation
- Unsupported incident categories
- DIY log-audit MCP (use `cls-log-mcp`)

---

## 4. Orchestrator State Machine

### States
- `INTAKE`
- `CLASSIFY`
- `PLAN`
- `COLLECT_EVIDENCE`
- `UPDATE_HYPOTHESES`
- `VERIFY`
- `SUMMARIZE`
- `DONE`
- `BLOCKED`
- `FAILED`

### Transitions
- `INTAKE -> CLASSIFY`
- `CLASSIFY -> PLAN`
- `PLAN -> COLLECT_EVIDENCE`
- `COLLECT_EVIDENCE -> UPDATE_HYPOTHESES`
- `UPDATE_HYPOTHESES -> VERIFY`
- `VERIFY -> COLLECT_EVIDENCE` (if more evidence needed)
- `VERIFY -> SUMMARIZE` (if confidence sufficient)
- `SUMMARIZE -> DONE`
- any -> `BLOCKED` / `FAILED` as appropriate

> Implement as **plain Python enum + methods**, no state-machine framework.

---

## 5. Domain Models

### Incident
- incident_id
- raw_description
- normalized_summary
- service_name
- time_window
- environment
- issue_category
- extracted_signals
- missing_context

### Evidence
- evidence_id
- source (`cls-log-mcp` | MySQL | Chrome | other)
- tool_name
- summary
- structured_data
- implication (`supports`|`contradicts`|`neutral`)
- confidence
- timestamp
- trace_id
- sensitive

### Hypothesis
- hypothesis_id
- title
- description
- supporting_evidence_ids
- contradicting_evidence_ids
- missing_evidence
- confidence
- status (`candidate` | `likely` | `ruled_out` | `confirmed`)

### InvestigationState
- incident
- current_state
- tool_call_count
- max_tool_calls
- evidence_list
- hypothesis_list
- ruled_out_hypotheses
- open_questions
- execution_log

### RCAReport
- incident_summary
- most_likely_root_cause
- confidence_level
- supporting_evidence
- ruled_out_alternatives
- remaining_unknowns
- recommended_next_actions

---

## 6. Skills Specification (Markdown Playbooks)

### incident_intake.md
- Transform raw issue into structured incident
- Extract symptom, service/API, timeframe, ambiguity

### log_triage.md
- Guide model to interpret logs from `cls-log-mcp`
- Emphasize clustering, error signature, trace correlation, filtering noise

### mysql_rca.md
- Guide diagnosis using MySQL MCP read-only queries
- Highlight locks, rollbacks, missing records, slow queries

### cloud_console_inspection.md
- Guide reasoning on Chrome MCP observations
- Focus on alerts, metrics, config drift, deployment changes

### hypothesis_ranking.md
- Rank candidate hypotheses based on supporting/contradicting evidence
- Prefer evidence-rich explanations

### rca_report.md
- Enforce structured report
- Include uncertainty, recommended next steps

---

## 7. MCP Connector Rules

- Orchestrator must call MCPs via connectors only
- Connector return must normalize to Evidence objects
- For logs, **always use `cls-log-mcp`**. No custom log MCP
- Connector failures: classify as transient / permanent / semantic; only retry transient

---

## 8. Investigation Lifecycle

1. **Intake** → normalize incident
2. **Classify** → determine category and suspicion areas
3. **Plan** → bounded investigation plan (tool sequence, max calls)
4. **Collect Evidence** → call MCPs: `cls-log-mcp`, Chrome, MySQL
5. **Update Hypotheses** → maintain support/contradiction, missing evidence, confidence
6. **Verify** → gather additional evidence for top hypotheses
7. **Summarize** → generate structured RCA report
8. **Done** → output report

---

## 9. Report Format

```md
## Incident Summary
...

## Most Likely Root Cause
...

## Confidence
High | Medium | Low

## Supporting Evidence
1. ...
2. ...
3. ...

## Ruled Out Alternatives
- ...
- ...

## Remaining Unknowns
- ...
- ...

## Recommended Next Actions
1. ...
2. ...
3. ...
```

---

## 10. Constraints & Rules

- Use **existing `cls-log-mcp`** for all log tasks
- Orchestrator must be plain Python
- Skills are guidance only, not execution engine
- Evidence must be normalized before hypothesis update
- Stop investigation if budget exhausted or no useful next step exists
- Always log actions for traceability
- Read-only for MySQL & browser MCP
- Do not implement custom log MCP

---

## 11. Suggested Project Structure

```text
cloud_incident_rca_agent/
├── app/
├── orchestrator/
│   ├── orchestrator.py
│   ├── state_machine.py
│   ├── planner.py
│   ├── tool_router.py
│   ├── evidence_store.py
│   ├── hypothesis_manager.py
│   ├── policies.py
│   └── report_builder.py
├── domain/
├── connectors/
│   ├── base_mcp_client.py
│   ├── chrome_client.py
│   ├── mysql_client.py
│   ├── cls_log_client.py
│   └── llm_client.py
├── skills/
├── prompts/
├── tests/
├── pyproject.toml
├── README.md
└── .env.example
```

> 这里 `cls_log_client.py` 是你调用 `cls-log-mcp` 的统一适配器，不要自己再写日志 MCP。

---

## 12. Implementation Order

1. Define domain models (Incident, Evidence, Hypothesis, RCAReport, InvestigationState)  
2. Implement orchestrator skeleton + state machine in plain Python  
3. Implement MCP connectors (`cls-log-mcp`, Chrome, MySQL)  
4. Add skill markdown assets  
5. Implement planner, evidence collection, hypothesis update, verify, summarize  
6. Implement scenario tests / replay fixtures  
7. Validate structured RCA report and confidence outputs

---

## 13. Definition of Done

The MVP is complete if:

- Incident intake works
- Evidence is collected via `cls-log-mcp` + other MCPs
- Evidence is normalized into Evidence objects
- At least 2 candidate hypotheses are generated and verified
- RCA report is structured, evidence-backed, and shows uncertainty
- Tests for at least 3 scenarios pass
- No custom log MCP implemented; all logs come from `cls-log-mcp`
