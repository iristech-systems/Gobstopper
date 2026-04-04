import json
import asyncio
import functools
from enum import Enum
from typing import AsyncGenerator, Callable, Any, Dict, Iterable, TypeAlias
from ..http.response import StreamResponse
from ..html._types import HasHtml, Renderable

FragmentLike: TypeAlias = str | HasHtml | Renderable


class MergeMode(Enum):
    """Datastar RC.8 patch-elements merge modes.

    Canonical names (prefer these in new code):
        REPLACE_ELEMENT  — replace the entire target element, tag included.
        REPLACE_CONTENT  — replace only the children of the target element.

    The names OUTER and INNER are kept as aliases for backwards compatibility
    but are deprecated.  They were confusing because "outer" sounds like the
    surrounding context rather than the element itself.

    Other modes:
        REPLACE  — hard-replace the element (resets DOM state, no morphing).
        REMOVE   — remove the target element from the DOM.
        PREPEND  — insert before the first child of the target.
        APPEND   — insert after the last child of the target.
        BEFORE   — insert before the target element itself.
        AFTER    — insert after the target element itself.
    """

    # Canonical names
    REPLACE_ELEMENT = "outer"  # Replace entire element (including its tag)
    REPLACE_CONTENT = "inner"  # Replace element's inner content only

    # Deprecated aliases kept for backwards compatibility
    OUTER = "outer"  # Deprecated: use REPLACE_ELEMENT
    INNER = "inner"  # Deprecated: use REPLACE_CONTENT

    # Other Datastar modes
    REPLACE = "replace"  # Hard-replace (resets DOM state)
    REMOVE = "remove"  # Remove target element
    PREPEND = "prepend"  # Insert before first child
    APPEND = "append"  # Insert after last child
    BEFORE = "before"  # Insert before target element
    AFTER = "after"  # Insert after target element


class Datastar:
    """Datastar RC.8 Hypermedia Extension for Gobstopper.

    Provides helpers for Server-Sent Events (SSE) and Datastar signal formatting.

    CDN (RC.8):
        <script type="module"
            src="https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.0-RC.8/bundles/datastar.js">
        </script>

    Available @action directives:
        @get, @post, @put, @patch, @delete  — backend HTTP actions (signals sent as query/body)
        @peek()     — read a signal without subscribing
        @setAll()   — set many signals matching a regex filter
        @toggleAll()— toggle boolean signals matching a regex filter
        @clipboard()— copy text to clipboard (pro)
        @fit()      — linear interpolation between value ranges (pro)
        @intl()     — locale-aware formatting (pro, added RC.8)

    Tailwind CDN / JIT warning:
        If you use Tailwind's CDN Play/JIT build, any CSS class that appears
        *only* in SSE-injected fragments (never in the initial HTML render) will
        be silently unstyled — Tailwind scans the initial document, not runtime
        patches.  Workarounds: use a full Tailwind build pipeline, or ensure
        every dynamic class is rendered somewhere in the first response.
    """

    # Valid modes for Datastar RC.8 patch-elements
    VALID_MODES = {
        "outer",
        "inner",
        "replace",
        "remove",
        "prepend",
        "append",
        "before",
        "after",
    }

    # Default free CDN URL
    _CDN_URL = "https://cdn.jsdelivr.net/gh/starfederation/datastar@v1.0.0-RC.8/bundles/datastar.js"

    @staticmethod
    def script_tag(pro_src: str = None) -> str:
        """Generate the Datastar ``<script>`` tag as an HTML string.

        For the **free** version, returns a tag pointing to the official CDN.
        For **Datastar Pro**, pass the path to your self-hosted Pro bundle
        (downloaded from https://data-star.dev/pro/download).

        Args:
            pro_src: Path to your self-hosted Datastar Pro JS bundle.
                e.g. ``"/static/js/datastar-pro.js"``.
                When ``None`` (default), the free CDN bundle is used.

        Returns:
            HTML ``<script type="module" src="...">`` string.

        Examples:
            Free bundle in a Jinja2 template::

                {{ datastar_script() }}
                {# or in Python: #}
                from gobstopper.extensions.datastar import Datastar
                head[Datastar.script_tag()]

            Pro self-hosted bundle::

                head[Datastar.script_tag(pro_src="/static/js/datastar-pro.js")]

        Note:
            Pro bundles are self-hosted — download yours from
            https://data-star.dev/pro/download after signing in with GitHub.
            Serve the file via ``StaticFileMiddleware`` or your CDN.
        """
        src = pro_src if pro_src else Datastar._CDN_URL
        return f'<script type="module" src="{src}"></script>'

    @staticmethod
    def stream(generator: AsyncGenerator[str, None]) -> StreamResponse:
        """Create a Datastar-compatible SSE stream response.

        Args:
            generator: Async generator yielding formatted signal strings.

        Returns:
            StreamResponse with 'text/event-stream' content type and no-cache headers.
        """
        return StreamResponse(
            generator,
            content_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    @staticmethod
    def normalize_fragment(fragment: FragmentLike) -> str:
        """Convert htpy/html objects to a single-line HTML fragment string."""
        if not isinstance(fragment, str):
            if hasattr(fragment, "__html__"):
                fragment = fragment.__html__()
            else:
                fragment = str(fragment)
        return " ".join(fragment.split())

    @staticmethod
    def merge_fragments(
        fragment: FragmentLike,
        selector: str = None,
        merge_mode: MergeMode = MergeMode.REPLACE_ELEMENT,
        settling_time: int = None,
    ) -> str:
        """Format a Datastar 'patch elements' SSE event (RC.8 format).

        The SSE protocol requires each ``data:`` line to contain exactly one
        line of text — embedded newlines would break the stream.  This method
        automatically collapses multi-line HTML fragments to a single line so
        callers never need to do it themselves.

        Args:
            fragment: HTML fragment string or any object with ``__html__`` /
                ``__str__`` (e.g. htpy elements).  Multi-line strings are
                normalised automatically.
            selector: CSS selector for the target element.  If omitted the
                method tries to extract the ``id`` from the fragment root tag
                and falls back to ``"body"``.
            merge_mode: How to apply the fragment (default: REPLACE_ELEMENT).
                See :class:`MergeMode` for all options.
            settling_time: Optional CSS transition settling time in ms.

        Returns:
            Formatted SSE string ready to be yielded from a generator.

        Raises:
            ValueError: If merge_mode carries an unrecognised value.

        RC.8 wire format::

            event: datastar-patch-elements
            data: selector #foo
            data: mode outer
            data: elements <div id="foo">…</div>
            <blank line>
        """
        import re

        # Support htpy elements and any __html__ object
        fragment = Datastar.normalize_fragment(fragment)

        # Validate mode
        if merge_mode.value not in Datastar.VALID_MODES:
            raise ValueError(
                f"Invalid merge mode '{merge_mode.value}'. "
                f"Valid modes: {', '.join(sorted(Datastar.VALID_MODES))}. "
                f"See: https://data-star.dev/reference/sse_events"
            )

        data_lines = []

        # Selector is required — auto-extract from fragment id if not given
        if not selector:
            id_match = re.search(r'id=["\']([^"\']+)["\']', fragment)
            selector = f"#{id_match.group(1)}" if id_match else "body"

        data_lines.append(f"selector {selector}")
        data_lines.append(f"mode {merge_mode.value}")

        if settling_time:
            data_lines.append(f"settle {settling_time}")

        data_lines.append(f"elements {fragment}")

        output = "event: datastar-patch-elements\n"
        for line in data_lines:
            output += f"data: {line}\n"
        output += "\n"
        return output

    @staticmethod
    def merge_many(
        fragments: Iterable[FragmentLike],
        selector: str = None,
        merge_mode: MergeMode = MergeMode.REPLACE_ELEMENT,
        settling_time: int = None,
    ) -> str:
        """Merge multiple fragments in one SSE payload string."""
        return "".join(
            Datastar.merge_fragments(
                frag,
                selector=selector,
                merge_mode=merge_mode,
                settling_time=settling_time,
            )
            for frag in fragments
        )

    @staticmethod
    def patch_signals(signals: Dict[str, Any], only_if_missing: bool = False) -> str:
        """Format a Datastar 'patch signals' SSE event.

        This allows you to update reactive signals on the client without patching HTML.
        Useful for updating state, showing/hiding elements, or triggering client-side effects.

        Args:
            signals: Dictionary of signal names to values. Set value to None to remove a signal.
            only_if_missing: If True, only set signals that don't already exist on the client.

        Returns:
            Formatted SSE data string.

        Examples:
            >>> # Update cart count and total
            >>> Datastar.patch_signals({"cartCount": 3, "cartTotal": 99.99})

            >>> # Remove a signal
            >>> Datastar.patch_signals({"tempMessage": None})

            >>> # Only set if not already defined
            >>> Datastar.patch_signals({"userId": 123}, only_if_missing=True)
        """
        # Format signals as JavaScript object notation
        signals_str = json.dumps(signals)

        output = "event: datastar-patch-signals\n"
        if only_if_missing:
            output += "data: onlyIfMissing true\n"
        output += f"data: signals {signals_str}\n"
        output += "\n"
        return output

    @staticmethod
    def signal(signal: str) -> str:
        """Raw signal helper."""
        return f"data: {signal}\n\n"


def datastar_stream(
    selector: str,
    mode: MergeMode = MergeMode.REPLACE_ELEMENT,
    interval: float = 1.0,
    settling_time: int = None,
):
    """Decorator to simplify Datastar SSE streaming endpoints.

    Converts a simple function that returns HTML into a streaming SSE endpoint.
    The decorated function can be sync or async and should return an HTML
    fragment string (or htpy element).  Multi-line fragments are normalised
    automatically — no need for a _merge_single_line helper.

    Args:
        selector: CSS selector for the target element.
        mode: Merge mode (default: REPLACE_ELEMENT — replaces the entire element).
        interval: Seconds between updates (default: 1.0).
        settling_time: Optional CSS transition settling time in ms.

    Returns:
        Decorated function that returns a StreamResponse.

    Examples:
        >>> from gobstopper.extensions.datastar import datastar_stream, MergeMode
        >>> from datetime import datetime
        >>>
        >>> @app.get("/clock")
        >>> @datastar_stream(selector="#clock", mode=MergeMode.REPLACE_ELEMENT, interval=0.1)
        >>> async def clock():
        >>>     now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        >>>     return f'<div id="clock" class="time">{now}</div>'

        >>> @app.get("/counter")
        >>> @datastar_stream(selector="#count", interval=1.0)
        >>> def counter():
        >>>     count = get_current_count()
        >>>     return f'<span id="count">{count}</span>'
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async def generator():
                while True:
                    # Call the function (handle both sync and async)
                    if asyncio.iscoroutinefunction(func):
                        html = await func(*args, **kwargs)
                    else:
                        html = func(*args, **kwargs)

                    # Format as Datastar SSE event
                    yield Datastar.merge_fragments(
                        html,
                        selector=selector,
                        merge_mode=mode,
                        settling_time=settling_time,
                    )

                    # Wait for next interval
                    await asyncio.sleep(interval)

            return Datastar.stream(generator())

        return wrapper

    return decorator


def fragment(
    html_fragment: FragmentLike,
    selector: str = None,
    merge_mode: MergeMode = MergeMode.REPLACE_ELEMENT,
    settling_time: int = None,
) -> str:
    """Small ergonomic alias for Datastar.merge_fragments()."""
    return Datastar.merge_fragments(
        html_fragment,
        selector=selector,
        merge_mode=merge_mode,
        settling_time=settling_time,
    )
