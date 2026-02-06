
import json
import asyncio
import functools
from enum import Enum
from typing import AsyncGenerator, Callable, Any, Dict
from ..http.response import StreamResponse

class MergeMode(Enum):
    """Valid Datastar RC.7 patch-elements modes."""
    OUTER = "outer"       # Replace entire element (including tag)
    INNER = "inner"       # Replace element's inner content only
    REPLACE = "replace"   # Alias for outer
    REMOVE = "remove"     # Remove target element
    PREPEND = "prepend"   # Insert before first child
    APPEND = "append"     # Insert after last child
    BEFORE = "before"     # Insert before target element
    AFTER = "after"       # Insert after target element

class Datastar:
    """Datastar Hypermedia Extension for Gobstopper.
    
    Provides helpers for Server-Sent Events (SSE) and strict Datastar signal formatting.
    """
    
    # Valid modes for Datastar RC.7 patch-elements
    VALID_MODES = {"outer", "inner", "replace", "remove", "prepend", "append", "before", "after"}
    
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
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )

    @staticmethod
    def merge_fragments(fragment: str, selector: str = None, merge_mode: MergeMode = MergeMode.OUTER, settling_time: int = None) -> str:
        """Format a Datastar 'patch elements' event (RC.7 format).
        
        Args:
            fragment: HTML fragment string or Object (converted to string).
            selector: CSS selector to target. If not provided, attempts to extract ID from fragment.
            merge_mode: Merge strategy (default: outer - replaces the entire element).
            settling_time: Time in ms to settle style transitions.
            
        Returns:
            Formatted SSE data string.
            
        Raises:
            ValueError: If merge_mode is invalid.
        """
        import re
        
        # Automatically convert Element objects (like htpy elements) to string
        if not isinstance(fragment, str):
            fragment = str(fragment)
        
        # Validate mode
        if merge_mode.value not in Datastar.VALID_MODES:
            raise ValueError(
                f"Invalid merge mode '{merge_mode.value}'. "
                f"Valid modes are: {', '.join(sorted(Datastar.VALID_MODES))}. "
                f"See: https://data-star.dev/reference/sse_events#datastar-patch-elements"
            )
        
        data_lines = []
        
        # Selector is REQUIRED in RC.7 - extract from fragment ID if not provided
        if not selector:
            # Try to extract id from the fragment
            id_match = re.search(r'id=["\']([^"\']+)["\']', fragment)
            if id_match:
                selector = f"#{id_match.group(1)}"
            else:
                # Fallback to body if no ID found
                selector = "body"
        
        data_lines.append(f"selector {selector}")
        
        # Mode (inner, outer, morph, etc.)
        data_lines.append(f"mode {merge_mode.value}")
        
        # Optional settling time
        if settling_time:
             data_lines.append(f"settle {settling_time}")
             
        # The HTML elements to patch
        data_lines.append(f"elements {fragment}")
        
        # Datastar RC.7 format:
        # event: datastar-patch-elements
        # data: selector #foo (REQUIRED)
        # data: mode inner
        # data: elements <div>...</div>
        
        output = "event: datastar-patch-elements\n"
        for line in data_lines:
            output += f"data: {line}\n"
        output += "\n"
        return output

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
    mode: MergeMode = MergeMode.OUTER,
    interval: float = 1.0,
    settling_time: int = None
):
    """Decorator to simplify Datastar SSE streaming endpoints.
    
    Converts a simple function that returns HTML into a streaming SSE endpoint.
    The decorated function can be sync or async, and should return HTML fragments.
    
    Args:
        selector: CSS selector for the target element.
        mode: Merge mode (default: OUTER - replaces entire element).
        interval: Seconds between updates (default: 1.0).
        settling_time: Optional CSS transition settling time in ms.
        
    Returns:
        Decorated function that returns a StreamResponse.
        
    Examples:
        >>> from gobstopper.ext.datastar import datastar_stream, MergeMode
        >>> from datetime import datetime
        >>>
        >>> @app.get("/clock")
        >>> @datastar_stream(selector="#clock", mode=MergeMode.OUTER, interval=0.1)
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
                        settling_time=settling_time
                    )
                    
                    # Wait for next interval
                    await asyncio.sleep(interval)
            
            return Datastar.stream(generator())
        
        return wrapper
    return decorator
