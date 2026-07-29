from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.errors import error_detail
from app.models import Notification, User
from app.schemas import NotificationCreate, NotificationOut, NotificationUpdate

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(status: str | None = None, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    stmt = select(Notification).order_by(Notification.created_at.desc())
    if status:
        stmt = stmt.where(Notification.status == status)
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=NotificationOut)
def create_notification(payload: NotificationCreate, db: Session = Depends(get_db)):
    """Called by the AI Platform's Communication Agent."""
    notification = Notification(**payload.model_dump())
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


@router.patch("/{notification_id}", response_model=NotificationOut)
def update_notification(
    notification_id: str, payload: NotificationUpdate, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
):
    if payload.status not in {"read", "archived", "unread"}:
        raise HTTPException(
            status_code=400, detail=error_detail("invalid_notification_status", allowed="unread, read, archived")
        )

    notification = db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail=error_detail("notification_not_found"))

    notification.status = payload.status
    db.commit()
    db.refresh(notification)
    return notification
