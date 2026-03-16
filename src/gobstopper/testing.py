"""
Test client for Gobstopper applications.

Drives the app's RSGI entry point directly — no real server needed.

Usage::

    from gobstopper import Gobstopper
    from gobstopper.testing import TestClient

    app = Gobstopper(__name__)

    @app.get("/hello")
    async def hello(request):
        return {"message": "hi"}

    with TestClient(app) as client:
        r = client.get("/hello")
        assert r.status == 200
        assert r.json() == {"message": "hi"}
"""
from __future__ import annotations

import asyncio
import urllib.parse
from types import SimpleNamespace
from typing import Any

import msgspec


class _FakeTransport:
    """Collects streamed chunks sent via response_stream."""

    def __init__(self, proto: "_FakeProtocol"):
        self._proto = proto

    async def send_str(self, s: str) -> None:
        self._proto.body += s.encode()

    async def send_bytes(self, b: bytes) -> None:
        self._proto.body += b


class _FakeProtocol:
    """Captures whatever response_* call the handler makes."""

    def __init__(self, body_bytes: bytes = b""):
        self._injected_body = body_bytes
        self.status: int | None = None
        self.rsgi_headers: list[tuple[str, str]] = []
        self.body: bytes = b""

    # RSGI body-read callable — the request object calls this to get the body.
    async def __call__(self) -> bytes:
        return self._injected_body

    def response_str(self, status: int, headers, body: str) -> None:
        self.status = status
        self.rsgi_headers = list(headers)
        self.body = body.encode()

    def response_bytes(self, status: int, headers, body: bytes) -> None:
        self.status = status
        self.rsgi_headers = list(headers)
        self.body = body

    def response_file(self, status: int, headers, path: str) -> None:
        self.status = status
        self.rsgi_headers = list(headers)
        with open(path, "rb") as f:
            self.body = f.read()

    def response_file_range(self, status: int, headers, path: str, start: int, end: int) -> None:
        self.status = status
        self.rsgi_headers = list(headers)
        with open(path, "rb") as f:
            f.seek(start)
            self.body = f.read(end - start)

    def response_stream(self, status: int, headers) -> _FakeTransport:
        self.status = status
        self.rsgi_headers = list(headers)
        return _FakeTransport(self)


class TestResponse:
    """Wraps the result captured by _FakeProtocol."""

    def __init__(self, status: int, rsgi_headers: list[tuple[str, str]], body: bytes):
        self.status = status
        self.headers: dict[str, str] = {k.lower(): v for k, v in rsgi_headers}
        self.body = body

    def json(self) -> Any:
        return msgspec.json.decode(self.body)

    def text(self) -> str:
        return self.body.decode()

    def get_cookie(self, name: str) -> str | None:
        """Return the value of a Set-Cookie header for *name*, or None."""
        raw = self.headers.get("set-cookie", "")
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith(f"{name}="):
                return part[len(name) + 1:]
        return None


class TestClient:
    """
    Synchronous test client that drives the app's RSGI entry point directly.

    Use as a context manager — startup hooks fire on ``__enter__``,
    shutdown hooks fire on ``__exit__``::

        with TestClient(app) as client:
            r = client.get("/ping")
            assert r.status == 200

    Args:
        app: A :class:`~gobstopper.Gobstopper` instance.
        raise_server_errors: If ``True`` (default), 5xx responses raise
            :exc:`AssertionError` so tests fail loudly.
    """

    def __init__(self, app: Any, raise_server_errors: bool = True):
        self.app = app
        self.raise_server_errors = raise_server_errors
        self._loop = asyncio.new_event_loop()

    def __enter__(self) -> "TestClient":
        self._loop.run_until_complete(self.app._ensure_startup_complete())
        return self

    def __exit__(self, *_) -> None:
        self._loop.run_until_complete(self.app.shutdown())
        self._loop.close()

    # ------------------------------------------------------------------
    # Internal request dispatcher
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query: str = "",
        body: bytes = b"",
    ) -> TestResponse:
        scope = SimpleNamespace(
            proto="http",
            method=method.upper(),
            path=path,
            query_string=query,
            headers=headers or {},
            client=("testclient", 0),
        )
        proto = _FakeProtocol(body)
        self._loop.run_until_complete(self.app.__rsgi__(scope, proto))
        r = TestResponse(proto.status or 500, proto.rsgi_headers, proto.body)
        if self.raise_server_errors and r.status >= 500:
            raise AssertionError(f"Server error {r.status}:\n{r.text()}")
        return r

    # ------------------------------------------------------------------
    # Public HTTP verbs
    # ------------------------------------------------------------------

    def get(self, path: str, *, headers: dict[str, str] | None = None, params: dict | None = None) -> TestResponse:
        query = urllib.parse.urlencode(params) if params else ""
        return self._request("GET", path, headers=headers, query=query)

    def post(
        self,
        path: str,
        *,
        json: Any = None,
        data: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        hdrs = dict(headers or {})
        body = b""
        if json is not None:
            body = msgspec.json.encode(json)
            hdrs.setdefault("content-type", "application/json")
        elif data is not None:
            body = urllib.parse.urlencode(data).encode()
            hdrs.setdefault("content-type", "application/x-www-form-urlencoded")
        return self._request("POST", path, headers=hdrs, body=body)

    def put(
        self,
        path: str,
        *,
        json: Any = None,
        data: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        hdrs = dict(headers or {})
        body = b""
        if json is not None:
            body = msgspec.json.encode(json)
            hdrs.setdefault("content-type", "application/json")
        elif data is not None:
            body = urllib.parse.urlencode(data).encode()
            hdrs.setdefault("content-type", "application/x-www-form-urlencoded")
        return self._request("PUT", path, headers=hdrs, body=body)

    def patch(
        self,
        path: str,
        *,
        json: Any = None,
        data: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        hdrs = dict(headers or {})
        body = b""
        if json is not None:
            body = msgspec.json.encode(json)
            hdrs.setdefault("content-type", "application/json")
        elif data is not None:
            body = urllib.parse.urlencode(data).encode()
            hdrs.setdefault("content-type", "application/x-www-form-urlencoded")
        return self._request("PATCH", path, headers=hdrs, body=body)

    def delete(self, path: str, *, headers: dict[str, str] | None = None) -> TestResponse:
        return self._request("DELETE", path, headers=headers)
