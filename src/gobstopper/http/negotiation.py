"""Content negotiation utilities for Gobstopper (RSGI).

Provides helpers to choose a representation based on the HTTP Accept header and
produce typed Response instances. Supports wildcards and q-values per RFC 9110.

Notes:
    These helpers operate at the application layer and do not alter protocol
    semantics. When no acceptable representation exists, callers should emit a
    406 response using the standard problem+json error shape.
"""

from __future__ import annotations
from typing import Any
import msgspec

from .response import Response, JSONResponse


def to_xml(obj: Any) -> bytes:
    """Serialize a basic Python object to XML bytes.

    This is a best-effort serializer intended for simple dict/list/scalar
    payloads used in examples or debugging. It is not a general-purpose XML
    encoder and does not escape attribute values or handle namespaces.

    Args:
        obj: The value to serialize.

    Returns:
        XML document bytes encoded as UTF-8 with a root element.
    """
    import html

    def _to_xml(name: str, val: Any) -> str:
        if val is None:
            return f"<{name}/>"
        if isinstance(val, (str, int, float, bool)):
            return f"<{name}>{html.escape(str(val))}</{name}>"
        if isinstance(val, list):
            item_name = name[:-1] if name.endswith('s') and len(name) > 1 else 'item'
            return ''.join(_to_xml(item_name, x) for x in val)
        if isinstance(val, dict):
            inner = ''.join(_to_xml(k, v) for k, v in val.items())
            return f"<{name}>{inner}</{name}>"
        # Fallback for unsupported types
        return f"<{name}>{html.escape(str(val))}</{name}>"

    xml = '<?xml version="1.0" encoding="UTF-8"?>' + _to_xml('root', obj)
    return xml.encode('utf-8')


def _parse_accept(accept: str | None) -> list[tuple[str, float]]:
    """Parse an Accept header into (mime, q) pairs sorted by preference."""
    if not accept or accept.strip() == '':
        return [('*/*', 1.0)]
    parts = [p.strip() for p in accept.split(',') if p.strip()]
    result: list[tuple[str, float]] = []
    for p in parts:
        if ';' in p:
            mime, *params = [x.strip() for x in p.split(';')]
            q = 1.0
            for prm in params:
                if prm.startswith('q='):
                    try:
                        q = float(prm[2:])
                    except ValueError:
                        q = 0.0
            result.append((mime, q))
        else:
            result.append((p, 1.0))

    # Sort by q desc, then specificity (type/subtype > type/* > */*), then by param count desc
    def _specificity_key(mime: str) -> tuple[int, int]:
        base = mime.split(';', 1)[0].strip()
        params = mime.count(';')
        if base == '*/*':
            return (0, params)
        if base.endswith('/*'):
            return (1, params)
        return (2, params)

    result.sort(key=lambda t: (t[1], *_specificity_key(t[0])), reverse=True)
    return result


def negotiate(accept_header: str | None, producers: list[str]) -> str:
    """Choose the best producer given an Accept header.

    Supports */* and type/* wildcards and q-values per RFC 9110.

    Args:
        accept_header: Raw Accept header string, or None.
        producers: Ordered list of producible content types.

    Returns:
        The chosen content type from producers.

    Raises:
        ValueError: If no acceptable representation exists.
    """
    accepted = _parse_accept(accept_header)
    for mime, _ in accepted:
        if mime == '*/*':
            return producers[0]
        if '/*' in mime:
            prefix = mime.split('/', 1)[0]
            for p in producers:
                if p.startswith(prefix + '/'):
                    return p
        else:
            for p in producers:
                if p == mime:
                    return p
    # If nothing matched explicitly but */* present with lowest q, default to first
    if any(m == '*/*' for m, _ in accepted):
        return producers[0]
    raise ValueError('Not Acceptable')


def to_json(obj: Any) -> bytes:
    """Encode a Python object to JSON bytes using msgspec."""
    return msgspec.json.encode(obj)


async def negotiate_response(request, data: Any, producers: list[str] | None = None) -> Response:
    """Produce a Response that satisfies the request's Accept header.

    Handles JSON, HTML, and XML representations by default. When an acceptable
    type cannot be negotiated, a 406 application/problem+json is returned via
    the application's _problem() helper.

    Args:
        request: Current HTTP Request. Only headers and app are accessed.
        data: The payload or pre-constructed Response for HTML path.
        producers: Optional ordered list of content types to consider. Defaults
            to ["application/json", "text/html", "application/xml"].

    Returns:
        A concrete Response instance matching the negotiated content type.

    Notes:
        For HTML, if data is a Response it is passed through. If a dict with a
        "template" key is provided, the error template engine is used to render
        the template with optional context.
    """
    from .response import Response as _Resp  # avoid circular type issues

    producers = producers or ["application/json", "text/html", "application/xml"]
    try:
        chosen = negotiate(request.headers.get('accept'), producers)
    except ValueError:
        # 406 via app._problem
        return request.app._problem("Not Acceptable", 406)

    if chosen == 'application/json':
        return JSONResponse(data)

    if chosen == 'text/html':
        if isinstance(data, _Resp):
            return data
        # Template hint: {"template": "name.html", "context": {...}}
        if isinstance(data, dict) and 'template' in data:
            tpl = data.get('template')
            ctx = data.get('context', {})
            html_body = await request.app._error_template_engine.render_template_async(tpl, **(ctx or {}))
            return _Resp(html_body, content_type='text/html')
        # Fallback: pretty JSON in <pre>
        import json as _json
        pretty = _json.dumps(data, indent=2, ensure_ascii=False)
        html_body = f"<pre>{pretty}</pre>"
        return _Resp(html_body, content_type='text/html')

    if chosen == 'application/xml':
        xml_bytes = to_xml(data)
        return _Resp(xml_bytes, content_type='application/xml')

    return request.app._problem("Not Acceptable", 406)
