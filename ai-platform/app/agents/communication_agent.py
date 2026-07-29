"""Communication Agent.

Purpose: convert system events into human communication (emails,
notifications, chat responses, approval requests).
"""

import time

from sqlalchemy.orm import Session

from app.tools.audit import log_audit
from app.tools.communication import call_rest_api, send_email


def notify_approval_requested(db: Session, workflow_id: str, title: str, entity_type: str) -> dict:
    start = time.perf_counter()

    call_rest_api(
        "POST",
        "/api/notifications",
        json={
            "channel": "in_app",
            "subject": f"Approval requested: {title}",
            "body": f"A new {entity_type} '{title}' is awaiting your approval.",
            "related_workflow_id": workflow_id,
        },
    )

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="communication_agent",
        action="notify_approval_requested",
        duration_ms=duration_ms,
        final_response=f"notification created for workflow {workflow_id}",
    )
    return {"status": "sent", "workflow_id": workflow_id}


def notify_published(db: Session, requested_by: str, title: str, entity_type: str) -> dict:
    start = time.perf_counter()

    result = send_email(
        to=requested_by,
        subject=f"Published: {title}",
        body=f"Your {entity_type} '{title}' has been approved and published.",
    )

    duration_ms = int((time.perf_counter() - start) * 1000)
    log_audit(
        db,
        agent="communication_agent",
        action="notify_published",
        duration_ms=duration_ms,
        final_response=str(result),
    )
    return result
