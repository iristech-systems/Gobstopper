"""Server-Sent Events helpers for Gobstopper.

Provides formatting and a typed StreamResponse wrapper that sets correct
headers and handles UTF-8 encoding. SSE streams benefit from Granian's
response_stream backpressure; each yielded chunk is written as-is.
"""
from __future__ import annotations
from typing import AsyncIterator, AsyncIterable

from .response import StreamResponse


def format_sse(event: str | None = None, data: str = "", id: str | None = None, retry: int | None = None) -> bytes:
    """Format a single Server-Sent Event frame.

    Args:
        event: Optional event type name.
        data: Event data payload. Newlines are split and each line prefixed with
            "data: ". If empty, an empty data line is emitted.
        id: Optional event ID for reconnection sequencing.
        retry: Optional reconnection time in milliseconds for the client.

    Returns:
        Encoded bytes for one SSE frame ending with a blank line.

    Notes:
        Per the SSE spec, each event is delimited by a double newline. The
        function ensures at least one data line is present.
    """
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    if id:
        lines.append(f"id: {id}")
    if retry is not None:
        lines.append(f"retry: {int(retry)}")
    # Ensure at least one data line exists per event
    data_str = str(data)
    data_lines = data_str.splitlines() or [""]
    for line in data_lines:
        lines.append(f"data: {line}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


class SSEStream(StreamResponse):
    """Server‑Sent Events stream response.

    Wraps an async generator or iterable yielding bytes or str and sets the
    necessary SSE headers. Str chunks are encoded as UTF-8.

    Args:
        gen: Async iterator/iterable of bytes or str chunks already formatted as
            SSE frames (use format_sse) or raw data to be framed upstream.

    Notes:
        - Content-Type is set to ``text/event-stream; charset=utf-8``.
        - Backpressure is handled by Granian's response_stream transport.
        - Keep-Alive and no-cache headers are set for compatibility.
    """

    def __init__(self, gen: AsyncIterator[bytes | str] | AsyncIterable[bytes | str]):
        async def _gen():
            async for chunk in gen:  # type: ignore[attr-defined]
                yield chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")

        super().__init__(
            _gen,
            headers={
                "content-type": "text/event-stream; charset=utf-8",
                "cache-control": "no-cache",
                "connection": "keep-alive",
            },
        )
