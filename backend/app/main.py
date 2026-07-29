import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db import init_db
from app.observability import setup_observability
from app.routers import ai_proxy, auth, health, notifications, workflows
from app.seed import seed_demo_users

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Backend",
    description="Business backend: auth (editor/reviewer roles), workflows, notifications; proxies AI requests to the AI Platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(workflows.router)
app.include_router(notifications.router)
app.include_router(ai_proxy.router)
setup_observability(app, service_name="backend")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """FastAPI's default handler returns raw (English-only) Pydantic
    messages under `detail`; the web console can't localize those. Return a
    generic structured code instead — field-level detail still goes to the
    server log via the default logger, just not to the client."""
    return JSONResponse(status_code=422, content={"detail": {"error_code": "validation_error", "params": {}}})


@app.on_event("startup")
def on_startup():
    init_db()
    seed_demo_users()
