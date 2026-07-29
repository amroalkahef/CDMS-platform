"""Structured domain errors.

Plain `ValueError(f"...")` bakes an English sentence into the exception,
which `api/routes.py` used to forward verbatim as the HTTP error `detail` —
so the web console showed raw English even when the UI was in Arabic.
`DomainError` instead carries a stable `code` plus machine-readable
`params`, so the API layer can build `{"error_code": ..., "params": ...}`
and the frontend can look the code up in its own translated message table.
"""


class DomainError(ValueError):
    def __init__(self, code: str, **params):
        self.code = code
        self.params = params
        super().__init__(code)


def error_detail(exc: Exception) -> dict:
    """Best-effort structured `detail` payload for an HTTPException raised
    from a caught exception. Falls back to a generic code for plain
    `ValueError`s that haven't been converted to `DomainError` yet."""
    if isinstance(exc, DomainError):
        return {"error_code": exc.code, "params": exc.params}
    return {"error_code": "validation_error", "params": {"message": str(exc)}}
