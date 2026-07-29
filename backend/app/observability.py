"""Phase 5 (Production) — Monitoring & Logging.

Prometheus metrics are always on (`/metrics`). OpenTelemetry tracing is
opt-in: only activates if OTEL_EXPORTER_OTLP_ENDPOINT is set, so the base
docker-compose stack doesn't need a collector running to boot cleanly.
"""

import logging
import os

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

logger = logging.getLogger("backend.observability")


def setup_observability(app: FastAPI, service_name: str) -> None:
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not otlp_endpoint:
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — tracing disabled (metrics still available at /metrics)")
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    from app.db import engine

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument(engine=engine)

    logger.info("OpenTelemetry tracing enabled, exporting to %s", otlp_endpoint)
