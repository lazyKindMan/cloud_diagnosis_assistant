"""Shared enum types for the RCA domain."""

from enum import StrEnum


class InvestigationStatus(StrEnum):
    """Explicit states for the bounded investigation lifecycle."""

    INTAKE = "INTAKE"
    CLASSIFY = "CLASSIFY"
    PLAN = "PLAN"
    COLLECT_EVIDENCE = "COLLECT_EVIDENCE"
    UPDATE_HYPOTHESES = "UPDATE_HYPOTHESES"
    VERIFY = "VERIFY"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    SUMMARIZE = "SUMMARIZE"
    DONE = "DONE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class EvidenceSource(StrEnum):
    """Systems that can provide investigation evidence."""

    CLS_LOG_MCP = "cls-log-mcp"
    MYSQL = "MySQL"
    CHROME = "Chrome"
    OTHER = "other"


class EvidenceImplication(StrEnum):
    """How a piece of evidence affects a hypothesis."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    NEUTRAL = "neutral"


class HypothesisStatus(StrEnum):
    """Lifecycle state for an RCA hypothesis."""

    CANDIDATE = "candidate"
    LIKELY = "likely"
    RULED_OUT = "ruled_out"
    CONFIRMED = "confirmed"


class ConfidenceLevel(StrEnum):
    """Human-readable confidence used in RCA reports."""

    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ToolTarget(StrEnum):
    """External systems that tool intents can target."""

    CLS_LOG_MCP = "cls-log-mcp"
    CHROME = "Chrome"
    MYSQL = "MySQL"
    OTHER = "other"


class ConnectorErrorCategory(StrEnum):
    """Operational class for connector failures."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    SEMANTIC = "semantic"
    POLICY = "policy"


class RiskLevel(StrEnum):
    """Risk level assigned to human review requests."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HumanReviewDecisionStatus(StrEnum):
    """Reviewer decision state for gated orchestration actions."""

    APPROVED = "approved"
    REJECTED = "rejected"
    APPROVED_WITH_MODIFICATIONS = "approved_with_modifications"


class EvidenceRequestKind(StrEnum):
    """Kinds of evidence acquisition requests."""

    LOG = "log"
    CODE = "code"
    SQL = "sql"


class LogEvidenceRoute(StrEnum):
    """Routes available for acquiring log evidence."""

    CLS_MCP = "cls_mcp"
    CHROME_MCP = "chrome_mcp"
    LOCAL_FILE = "local_file"


class EvidenceRequestStatus(StrEnum):
    """Execution or policy outcome for one evidence request."""

    EXECUTED = "executed"
    SKIPPED = "skipped"
    POLICY_BLOCKED = "policy_blocked"
    REQUIRES_REVIEW = "requires_review"
    FAILED = "failed"


class ReplanAction(StrEnum):
    """Policy action after one evidence round."""

    REPLAN = "replan"
    SUMMARIZE = "summarize"
    BLOCK = "block"
    HUMAN_REVIEW = "human_review"


class StopReason(StrEnum):
    """Structured reason for stopping or continuing an evidence loop."""

    ROOT_CAUSE_CONFIDENT = "root_cause_confident"
    PLAN_ROUND_BUDGET_EXHAUSTED = "plan_round_budget_exhausted"
    TOOL_BUDGET_EXHAUSTED = "tool_budget_exhausted"
    NO_NEW_EVIDENCE = "no_new_evidence"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    POLICY_BLOCKED = "policy_blocked"
    REPEATED_FAILED_REQUESTS = "repeated_failed_requests"


class AgentSessionStatus(StrEnum):
    """Lifecycle status for one RCA investigation session."""

    RUNNING = "running"
    PENDING_REVIEW = "pending_review"
    DONE = "done"
    BLOCKED = "blocked"
    FAILED = "failed"


class CodeReadStrategy(StrEnum):
    """Strategy for local code evidence acquisition."""

    SEARCH_FIRST = "search_first"
    DIRECT_PATH = "direct_path"


class SqlResultShape(StrEnum):
    """Expected shape of a SQL validation query result."""

    SINGLE_ROW = "single_row"
    ROWS = "rows"
    COUNT = "count"
    AGGREGATE = "aggregate"
