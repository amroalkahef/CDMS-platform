"""Seeds two demo accounts (editor/reviewer) on startup so the roles are
usable immediately without a registration step. Idempotent — skips any
email that already exists."""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security import hash_password

DEMO_USERS = [
    {"name": "Dana Editor", "email": "editor@demo.local", "password": "Editor123!", "role": "editor"},
    {"name": "Rami Reviewer", "email": "reviewer@demo.local", "password": "Reviewer123!", "role": "reviewer"},
]


def seed_demo_users() -> None:
    db = SessionLocal()
    try:
        for demo in DEMO_USERS:
            exists = db.execute(select(User).where(User.email == demo["email"])).scalar_one_or_none()
            if exists:
                continue
            db.add(
                User(
                    name=demo["name"],
                    email=demo["email"],
                    password_hash=hash_password(demo["password"]),
                    role=demo["role"],
                )
            )
        db.commit()
    finally:
        db.close()
