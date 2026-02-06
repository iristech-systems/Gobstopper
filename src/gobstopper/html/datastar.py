"""
htpy helpers for Datastar attributes.

This module provides helper functions to generate type-safe Datastar attributes
for use with htpy elements.

Usage:
    from gobstopper.html import div, input, span, button
    from gobstopper.html.datastar import bind, on_click, text, show
    
    # Type-safe Datastar attributes
    div[
        input(**bind("username")),
        span(**text("$count")),
        button(**on_click("@post('/submit')"))
    ]
"""

from typing import Dict, Any, Optional, Union
import json

# =============================================================================
# Event Handlers
# =============================================================================

def on(event: str, action: str, **modifiers) -> Dict[str, str]:
    """
    Generic event handler with modifiers.
    
    Args:
        event: The event name (e.g., 'click', 'input', 'custom-event')
        action: The Datastar action (e.g., "@post('/submit')")
        **modifiers: Event modifiers (e.g., debounce=300, prevent=True, stop=True)
        
    Returns:
        Dict with the formatted data-on attribute
    """
    mod_list = []
    
    # Process modifiers in order
    # Special handling for duration/debounce/throttle which take values
    for k, v in modifiers.items():
        if v is True or v is None:
            mod_list.append(f"__{k}")
        elif v is False:
            continue
        else:
            mod_list.append(f"__{k}.{v}")
            
    mod_str = "".join(mod_list)
    return {f"data-on:{event}{mod_str}": action}

def on_click(action: str, **modifiers) -> Dict[str, str]:
    """Click event handler"""
    return on("click", action, **modifiers)

def on_input(action: str, debounce: Optional[int] = None, **modifiers) -> Dict[str, str]:
    """Input event handler with optional debounce"""
    if debounce:
        modifiers['debounce'] = f"{debounce}ms"
    return on("input", action, **modifiers)

def on_change(action: str, **modifiers) -> Dict[str, str]:
    """Change event handler"""
    return on("change", action, **modifiers)

def on_submit(action: str, prevent: bool = True, **modifiers) -> Dict[str, str]:
    """Form submit handler"""
    if prevent:
        modifiers['prevent'] = True
    return on("submit", action, **modifiers)

def on_keydown(action: str, key: Optional[str] = None, **modifiers) -> Dict[str, str]:
    """Keydown event handler, optionally for a specific key"""
    event = "keydown"
    if key:
        # Note: Datastar doesn't natively support key filtering in event name like Vue
        # But we can support window-level keys if needed
        pass
    return on(event, action, **modifiers)

def on_load(action: str, **modifiers) -> Dict[str, str]:
    """Load event handler"""
    return on("load", action, **modifiers)

# =============================================================================
# Bindings
# =============================================================================

def bind(name: str) -> Dict[str, str]:
    """Two-way data binding to a signal"""
    return {f"data-bind:{name}": ""}

def model(name: str) -> Dict[str, str]:
    """Alias for bind"""
    return bind(name)

# =============================================================================
# Visibility & Content
# =============================================================================

def text(expression: str) -> Dict[str, str]:
    """Reactive text content"""
    return {"data-text": expression}

def show(condition: str) -> Dict[str, str]:
    """Conditional visibility (toggles display: none)"""
    return {"data-show": condition}

def class_toggle(class_name: str, condition: str) -> Dict[str, str]:
    """Conditional class toggling"""
    return {f"data-class:{class_name}": condition}

def attr(name: str, expression: str) -> Dict[str, str]:
    """Reactive attribute value"""
    return {f"data-attr:{name}": expression}

# =============================================================================
# Reactivity & Signals
# =============================================================================

def signals(obj: Dict[str, Any], merge: bool = True) -> Dict[str, str]:
    """
    Initialize reactive signals.
    
    Args:
        obj: Dictionary of initial signal values
        merge: Whether to merge with existing signals (default True)
    """
    key = "data-signals"
    if not merge:
        # Datastar defaults to merging, check docs if there's an overwrite flag
        # For now we assume standard data-signals
        pass
    return {key: json.dumps(obj)}

def computed(name: str, expression: str) -> Dict[str, str]:
    """Define a computed signal derived from other signals"""
    return {f"data-computed:{name}": expression}

# =============================================================================
# Backend Communication (SSE)
# =============================================================================

def init(endpoint: str, method: str = "get") -> Dict[str, str]:
    """Initialize SSE connection"""
    return {"data-init": f"@{method}('{endpoint}')"}

def sse(endpoint: str) -> Dict[str, str]:
    """Alias for init with GET"""
    return init(endpoint, "get")

# =============================================================================
# Intersection Observer
# =============================================================================

def on_intersect(action: str, once: bool = False, threshold: Optional[float] = None, **modifiers) -> Dict[str, str]:
    """
    Intersection observer trigger.
    
    Args:
        action: Datastar action
        once: Only trigger once
        threshold: 0.0 to 1.0 visibility threshold
    """
    if once:
        modifiers['once'] = True
    if threshold is not None:
        # Convert 0.5 -> 50 for Datastar syntax if needed, or keep decimal
        # Datastar docs use .50 for 50% usually
        modifiers['threshold'] = str(threshold).lstrip('0')
    
    return on("intersect", action, **modifiers)

def lazy_load(endpoint: str) -> Dict[str, str]:
    """Helper for lazy loading content on intersection"""
    return on_intersect(f"@get('{endpoint}')", once=True)

# =============================================================================
# Intervals & Polling
# =============================================================================

def on_interval(action: str, duration: Union[int, str]) -> Dict[str, str]:
    """
    Trigger action on interval.
    
    Args:
        action: Datastar action
        duration: Duration string (e.g. '1s', '500ms') or int (ms)
    """
    if isinstance(duration, int):
        duration = f"{duration}ms"
    return {f"data-on-interval__duration.{duration}": action}
