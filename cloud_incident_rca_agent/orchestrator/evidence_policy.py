"""Policy and fingerprinting for evidence acquisition requests."""

from __future__ import annotations

import json
import re
from typing import Any

from cloud_incident_rca_agent.domain import (
    AgentSession,
    CodeEvidenceRequest,
    EvidenceRequestResult,
    EvidenceRequestStatus,
    InvestigationBudgets,
    LogEvidenceRequest,
    ReplanAction,
    ReplanDecision,
    RiskLevel,
    SqlEvidenceRequest,
    StopReason,
)


class EvidenceAcquisitionPolicy:
    """Enforces per-session evidence acquisition budgets and safety rules."""

    def fingerprint(self, request: Any) -> str:
        if isinstance(request, LogEvidenceRequest):
            payload = {
                "kind": request.kind.value,
                "route": request.route.value,
                "service_name": request.service_name,
                "time_window": request.time_window,
                "trace_id": request.trace_id,
                "keywords": sorted(term.lower() for term in request.keywords),
                "query": self._normalize_text(request.query or ""),
                "local_path_hint": request.local_path_hint,
            }
        elif isinstance(request, CodeEvidenceRequest):
            payload = {
                "kind": request.kind.value,
                "search_terms": sorted(term.lower() for term in request.search_terms),
                "path_allowlist": sorted(request.path_allowlist),
                "file_globs": sorted(request.file_globs),
            }
        elif isinstance(request, SqlEvidenceRequest):
            payload = {
                "kind": request.kind.value,
                "sql": self._normalize_sql(request.sql),
                "tables": sorted(table.lower() for table in request.tables),
                "validation_purpose": self._normalize_text(request.validation_purpose),
                "parameters": sorted(request.parameters),
            }
        else:
            payload = request.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def validate_request(
        self,
        session: AgentSession,
        request: Any,
    ) -> EvidenceRequestResult | None:
        fingerprint = self.fingerprint(request)
        if (
            session.budgets.forbid_duplicate_requests
            and fingerprint in session.memory.attempted_request_fingerprints
        ):
            return EvidenceRequestResult(
                request_id=request.request_id,
                success=False,
                status=EvidenceRequestStatus.POLICY_BLOCKED,
                message="duplicate evidence request blocked by session memory",
            )
        if request.requires_human_review or request.risk_level == RiskLevel.HIGH:
            return EvidenceRequestResult(
                request_id=request.request_id,
                success=False,
                status=EvidenceRequestStatus.REQUIRES_REVIEW,
                message="evidence request requires human review",
            )
        return None

    def decide_after_round(
        self,
        *,
        session: AgentSession,
        request_results: list[EvidenceRequestResult],
        top_confidence: float,
    ) -> ReplanDecision:
        budgets: InvestigationBudgets = session.budgets
        remaining_rounds = max(budgets.max_plan_rounds - session.round_number, 0)
        if top_confidence >= budgets.min_confidence_to_summarize:
            return ReplanDecision(
                action=ReplanAction.SUMMARIZE,
                reason=StopReason.ROOT_CAUSE_CONFIDENT,
                remaining_rounds=remaining_rounds,
            )
        if remaining_rounds <= 0:
            return ReplanDecision(
                action=ReplanAction.BLOCK,
                reason=StopReason.PLAN_ROUND_BUDGET_EXHAUSTED,
                missing_evidence=session.memory.open_questions,
                remaining_rounds=0,
            )
        if any(result.status == EvidenceRequestStatus.REQUIRES_REVIEW for result in request_results):
            return ReplanDecision(
                action=ReplanAction.HUMAN_REVIEW,
                reason=StopReason.REQUIRES_HUMAN_REVIEW,
                missing_evidence=session.memory.open_questions,
                remaining_rounds=remaining_rounds,
            )
        return ReplanDecision(
            action=ReplanAction.REPLAN,
            reason=StopReason.NO_NEW_EVIDENCE,
            missing_evidence=session.memory.open_questions,
            remaining_rounds=remaining_rounds,
        )

    def _normalize_sql(self, sql: str) -> str:
        return re.sub(r"\s+", " ", sql.strip().lower())

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())
