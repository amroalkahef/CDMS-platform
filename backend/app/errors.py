"""Structured error details for HTTPException, mirroring
ai-platform/app/errors.py. `{"error_code": ..., "params": ...}` lets the web
console look the code up in its own translated message table instead of
rendering the raw (English-only) `detail` string."""


def error_detail(code: str, **params) -> dict:
    return {"error_code": code, "params": params}
