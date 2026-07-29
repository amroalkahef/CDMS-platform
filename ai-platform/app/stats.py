"""Dashboard analytics — plain reporting queries, not an agent responsibility
(no LLM calls, no writes)."""

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditLog, Circular, Decision

_ACTIVITY_ACTIONS = {
    "create_circular": "Created",
    "create_decision": "Created",
    "update_circular": "Updated",
    "update_decision": "Updated",
    "publish_circular": "Published",
    "publish_decision": "Activated",
    "delete_circular": "Deleted",
    "delete_decision": "Deleted",
}


def get_dashboard_stats(db: Session) -> dict:
    total_circulars = db.execute(select(func.count()).select_from(Circular)).scalar_one()
    total_decisions = db.execute(select(func.count()).select_from(Decision)).scalar_one()

    pending_drafts = db.execute(
        select(func.count()).select_from(Circular).where(Circular.status == "draft")
    ).scalar_one() + db.execute(select(func.count()).select_from(Decision).where(Decision.status == "draft")).scalar_one()

    published = db.execute(
        select(func.count()).select_from(Circular).where(Circular.status == "published")
    ).scalar_one() + db.execute(select(func.count()).select_from(Decision).where(Decision.status == "active")).scalar_one()

    recent_logs = db.execute(
        select(AuditLog)
        .where(AuditLog.agent == "execution_agent", AuditLog.action.in_(_ACTIVITY_ACTIONS.keys()))
        .order_by(AuditLog.created_at.desc())
        .limit(10)
    ).scalars().all()

    recent_activity = [
        {
            "action": _ACTIVITY_ACTIONS[log.action],
            "detail": log.final_response,
            "user": log.user_id,
            "timestamp": log.created_at.isoformat(),
        }
        for log in recent_logs
    ]

    today = date.today()
    horizon = today + timedelta(days=30)
    upcoming = db.execute(
        select(Circular)
        .where(
            Circular.publication_date.is_not(None),
            Circular.publication_date >= today,
            Circular.publication_date <= horizon,
            Circular.status != "published",
        )
        .order_by(Circular.publication_date.asc())
    ).scalars().all()

    upcoming_deadlines = [
        {
            "id": str(c.id),
            "title": c.title,
            "department": c.department,
            "publication_date": c.publication_date.isoformat(),
        }
        for c in upcoming
    ]

    return {
        "total_circulars": total_circulars,
        "total_decisions": total_decisions,
        "pending_drafts": pending_drafts,
        "published": published,
        "recent_activity": recent_activity,
        "upcoming_deadlines": upcoming_deadlines,
    }
