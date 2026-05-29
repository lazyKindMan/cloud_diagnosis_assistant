"""Build bounded LLM context from single-session memory."""

from __future__ import annotations

from cloud_incident_rca_agent.domain import AgentSession, ContextPacket


class ContextBuilder:
    """Compacts an RCA session into the context sent to planning LLM calls."""

    def build(self, session: AgentSession) -> ContextPacket:
        memory = session.memory
        incident_summary = memory.working_summary or session.raw_incident
        recent_rounds = memory.rounds[-3:]
        recent_evidence_summary = [
            (
                f"Round {item.round_number}: {item.objective}; "
                f"stop_reason={item.stop_reason.value}; "
                f"new_evidence={len(item.new_evidence_ids)}"
            )
            for item in recent_rounds
        ]
        remaining_rounds = max(
            session.budgets.max_plan_rounds - session.round_number + 1,
            0,
        )

        return ContextPacket(
            incident_summary=incident_summary,
            current_hypotheses=[],
            recent_evidence_summary=recent_evidence_summary,
            stable_facts=memory.stable_facts,
            open_questions=memory.open_questions,
            attempted_requests=memory.attempted_request_fingerprints,
            remaining_budgets={
                "rounds": remaining_rounds,
                "tool_calls": session.budgets.max_total_tool_calls,
                "code_files": session.budgets.max_code_files_per_round,
                "code_bytes_per_file": session.budgets.max_code_bytes_per_file,
                "sql_statements": session.budgets.max_sql_statements_per_round,
            },
        )
