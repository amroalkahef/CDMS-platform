import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("ai-platform.db")

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.commit()
    from app import models  # noqa: F401  (register models before create_all)

    Base.metadata.create_all(bind=engine)
    _patch_number_columns()


def _patch_number_columns() -> None:
    """No Alembic in this project (see create_all above) — patch the reference
    number columns onto tables that already existed before they were added,
    since create_all only creates missing tables, never missing columns."""
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE circulars ADD COLUMN IF NOT EXISTS circular_number VARCHAR(100)"))
        conn.commit()
        for table, column in (("circulars", "circular_number"), ("decisions", "decision_number")):
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_key UNIQUE ({column})"))
                conn.commit()
            except ProgrammingError:
                # constraint already exists, or legacy duplicate values block it
                conn.rollback()
                logger.info("Skipped unique constraint on %s.%s (already present or blocked by existing data)", table, column)
