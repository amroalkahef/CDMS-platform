from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, require_role
from app.clients import ai_platform_client
from app.db import get_db
from app.errors import error_detail
from app.models import Notification, User, Workflow, WorkflowStep
from app.schemas import DEFAULT_APPROVAL_CHAIN, WorkflowCreate, WorkflowDecision, WorkflowOut

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _with_steps():
    return select(Workflow).options(selectinload(Workflow.steps)).order_by(Workflow.created_at.desc())


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    status: str | None = None,
    entity_id: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = _with_steps()
    if status:
        stmt = stmt.where(Workflow.status == status)
    if entity_id:
        stmt = stmt.where(Workflow.entity_id == entity_id)
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=WorkflowOut)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    """Called by the AI Platform's Execution Agent (via CallRESTAPI, internal
    service-to-service — not reachable from the browser through the CORS'd
    public API surface in practice) when a draft is submitted for review.
    Builds the approval chain (default: single Reviewer step)."""
    chain = payload.approval_chain or DEFAULT_APPROVAL_CHAIN

    workflow = Workflow(
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        title=payload.title,
        requested_by=payload.requested_by,
        current_step_order=0,
    )
    db.add(workflow)
    db.flush()

    for order, role in enumerate(chain):
        db.add(WorkflowStep(workflow_id=workflow.id, step_order=order, role=role, status="pending"))

    db.commit()
    return db.execute(_with_steps().where(Workflow.id == workflow.id)).scalar_one()


@router.post("/{workflow_id}/decision", response_model=WorkflowOut)
def decide_workflow(
    workflow_id: str,
    payload: WorkflowDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("reviewer")),
):
    """The Reviewer's decision on the current step (PRD Step 12), reviewer-
    only. Approving does NOT publish — it marks the record 'approved' and
    hands it back to the Editor, who publishes explicitly. Rejecting sends
    it back to 'draft' with the reviewer's comment so the Editor can revise."""
    workflow = db.execute(_with_steps().where(Workflow.id == workflow_id)).scalar_one_or_none()
    if workflow is None:
        raise HTTPException(status_code=404, detail=error_detail("workflow_not_found"))
    if workflow.status != "pending_approval":
        raise HTTPException(status_code=409, detail=error_detail("workflow_already_decided", status=workflow.status))

    current_step = next((s for s in workflow.steps if s.step_order == workflow.current_step_order), None)
    if current_step is None:
        raise HTTPException(status_code=500, detail=error_detail("workflow_no_current_step"))

    current_step.decided_by = user.name
    current_step.decided_at = datetime.now(timezone.utc)
    current_step.comment = payload.comment

    if not payload.approve:
        current_step.status = "rejected"
        workflow.status = "rejected"
        for step in workflow.steps:
            if step.status == "pending" and step.step_order != current_step.step_order:
                step.status = "skipped"
        db.commit()

        ai_platform_client.update_entity(workflow.entity_type, workflow.entity_id, {"status": "draft", "updated_by": user.name})

        db.add(
            Notification(
                channel="in_app",
                subject=f"Rejected: {workflow.title}",
                body=f"{user.name} rejected '{workflow.title}'"
                + (f" — “{payload.comment}”" if payload.comment else "")
                + ". It has been returned to draft for revision.",
                related_workflow_id=str(workflow.id),
            )
        )
        db.commit()
        return db.execute(_with_steps().where(Workflow.id == workflow.id)).scalar_one()

    current_step.status = "approved"
    next_step = next((s for s in workflow.steps if s.step_order == current_step.step_order + 1), None)

    if next_step is None:
        workflow.status = "approved"
        db.commit()
        ai_platform_client.update_entity(workflow.entity_type, workflow.entity_id, {"status": "approved", "updated_by": user.name})
        db.add(
            Notification(
                channel="in_app",
                subject=f"Approved: {workflow.title}",
                body=f"{user.name} approved '{workflow.title}'"
                + (f" — “{payload.comment}”" if payload.comment else "")
                + ". It's ready to publish.",
                related_workflow_id=str(workflow.id),
            )
        )
        db.commit()
    else:
        workflow.current_step_order = next_step.step_order
        db.add(
            Notification(
                channel="in_app",
                subject=f"Approval requested: {workflow.title}",
                body=f"'{workflow.title}' needs {next_step.role} approval (step {next_step.step_order + 1} of {len(workflow.steps)}).",
                related_workflow_id=str(workflow.id),
            )
        )
        db.commit()

    return db.execute(_with_steps().where(Workflow.id == workflow.id)).scalar_one()
