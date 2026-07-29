"""SendEmail() / CallRESTAPI() shared tools.

SendEmail is stubbed to log-only by default (no SMTP creds configured in
the scaffold) so nothing accidentally emails anyone in dev. CallRESTAPI is
how the AI Platform reaches the (separate) business Backend service, e.g.
to register a workflow or create a notification.
"""

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("ai-platform.tools.communication")


def send_email(to: str, subject: str, body: str) -> dict:
    logger.info("SEND_EMAIL to=%s subject=%r", to, subject)
    return {"status": "logged", "to": to, "subject": subject}


def call_rest_api(method: str, path: str, json: dict | None = None) -> httpx.Response:
    settings = get_settings()
    url = f"{settings.backend_base_url}{path}"
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, url, json=json)
        response.raise_for_status()
        return response
