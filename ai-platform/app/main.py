import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.db import init_db
from app.errors import DomainError, error_detail
from app.observability import setup_observability

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="AI Platform",
    description="Orchestrator + specialist agents (Retrieval, Authoring, Validation, Execution, Communication).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
setup_observability(app, service_name="ai-platform")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Pydantic field validators (e.g. department/status enum checks in
    schemas.py) run during request-body parsing, before any route handler,
    so a `DomainError` raised there never reaches routes.py's try/except —
    FastAPI's default handler would otherwise return the exception's raw
    English `str()` under `detail`. Recover the original `DomainError` (kept
    on Pydantic's `ctx.error`) so the frontend still gets `{error_code,
    params}` instead of English text; fall back to a generic code for
    ordinary type/required-field validation errors."""
    for err in exc.errors():
        original = err.get("ctx", {}).get("error")
        if isinstance(original, DomainError):
            return JSONResponse(status_code=422, content={"detail": error_detail(original)})
    return JSONResponse(status_code=422, content={"detail": {"error_code": "validation_error", "params": {}}})


@app.on_event("startup")
def on_startup():
    init_db()
