from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .errors import ZJUError
from .security import sanitize_data


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def success(
    data: Any,
    *,
    page: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "ok": True,
        "data": sanitize_data(data),
        "page": page,
        "warnings": warnings or [],
        "fetched_at": now_rfc3339(),
    }


def failure(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ZJUError):
        code = exc.code
        message = exc.safe_message
        retryable = exc.retryable
        auth_required = exc.auth_required
    else:
        code = "internal_error"
        message = "The local ZJU tool failed without exposing sensitive diagnostics."
        retryable = False
        auth_required = False
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "auth_required": auth_required,
        },
        "fetched_at": now_rfc3339(),
    }
