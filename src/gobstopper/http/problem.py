"""
RFC 7807 Problem Details helper for Gobstopper

Provides a standardized way to return machine-readable error responses.
"""
from __future__ import annotations

from .response import JSONResponse


def problem(detail: str, status: int, *, type: str | None = None, title: str | None = None, **extras) -> JSONResponse:
    payload: dict[str, object] = {"detail": detail}
    if type:
        payload["type"] = type
    if title:
        payload["title"] = title
    if extras:
        payload.update(extras)
    resp = JSONResponse(payload, status=status)
    resp.headers["content-type"] = "application/problem+json"
    return resp
