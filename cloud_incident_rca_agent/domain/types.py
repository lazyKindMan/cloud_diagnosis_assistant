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
