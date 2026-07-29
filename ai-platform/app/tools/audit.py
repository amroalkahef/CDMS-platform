"""LogAudit() shared tool. Every agent call is logged per the PRD's
'Every AI action is logged / traced' core principle, and mirrored into
Prometheus metrics for the Monitoring dashboards."""

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.tools.metrics import record_agent_call


def log_audit(
    db: Session,
    agent: str,
    action: str,
    prompt: str = "",
    tokens: int = 0,
    cost: float = 0.0,
    duration_ms: int = 0,
    tool_calls: list | None = None,
    final_response: str = "",
    user_id: str = "dev-user",
    error: bool = False,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        agent=agent,
        action=action,
        prompt=prompt,
        tokens=tokens,
        cost=cost,
        duration_ms=duration_ms,
        tool_calls=tool_calls or [],
        final_response=final_response,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    record_agent_call(agent=agent, action=action, duration_ms=duration_ms, tokens=tokens, error=error)

    return entry
