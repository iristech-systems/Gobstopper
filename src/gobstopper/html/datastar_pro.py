"""
gobstopper.html.datastar_pro — HTML DSL helpers for Datastar Pro attributes.

Requires a Datastar Pro license and the Pro JS bundle.
Purchase and download: https://data-star.dev/pro

These helpers mirror the structure of ``gobstopper.html.datastar`` but cover
the Pro-only attributes and action expressions.  Importing this module is the
intent signal: if your project doesn't have a Pro license, don't import it.

Attribute helpers
-----------------
Each function returns a ``dict`` that can be unpacked as keyword arguments
into any htpy element call::

    from gobstopper.html import div, input as input_
    from gobstopper.html.datastar_pro import persist, custom_validity

    div(**persist())[
        input_(**custom_validity("$password === $confirm ? '' : 'Passwords must match'"))
    ]

Action expression helpers
-------------------------
``clipboard()``, ``fit()``, and ``intl()`` return *strings* for use inside
other attribute values (e.g. ``data-on:click``)::

    from gobstopper.html.datastar_pro import clipboard, fit, intl
    from gobstopper.html.datastar import on_click

    button(**on_click(clipboard("Hello, world!")))["Copy"]
    div(data_text=fit("$slider", 0, 100, 0, 255))

Bundle
------
Pro JS is self-hosted (download from your Pro portal, serve as a static
asset).  Use ``Datastar.script_tag(pro_src="/static/datastar-pro.js")``
from ``gobstopper.extensions.datastar`` to generate the correct ``<script>``
tag for your app.

Stellar CSS
-----------
Stellar CSS is a standalone CSS file — serve it like any static asset and
link it from your base template.  No Python-side integration required.

Datastar Inspector
------------------
The Inspector is a browser devtools extension — no Python-side integration
required.
"""

import json
from typing import Any, Dict, Optional, Union

# =============================================================================
# Pro Attributes
# =============================================================================

def animate(expression: str) -> Dict[str, str]:
    """Animate element attributes reactively over time.

    ``data-animate`` re-evaluates *expression* whenever any signal it reads
    changes and applies the result as CSS or attribute changes with animation.

    Args:
        expression: Datastar expression resolving to animation target values.

    Returns:
        ``{"data-animate": expression}``

    Example::

        div(**animate("$progress + '%'"))
    """
    return {"data-animate": expression}


def custom_validity(expression: str) -> Dict[str, str]:
    """Set a custom HTML5 form validation message reactively.

    ``data-custom-validity`` evaluates *expression* and calls
    ``setCustomValidity()`` on the element.  An empty string means the input
    is valid; any other string is shown as the browser's validation tooltip.

    Args:
        expression: Datastar expression returning ``""`` (valid) or an error
            message string.

    Returns:
        ``{"data-custom-validity": expression}``

    Example::

        input_(
            **bind("confirm_password"),
            **custom_validity("$password === $confirmPassword ? '' : 'Passwords must match'"),
        )
    """
    return {"data-custom-validity": expression}


def match_media(signal: str, query: str) -> Dict[str, str]:
    """Sync a boolean signal to a CSS media query.

    ``data-match-media:{signal}`` sets *signal* to ``True``/``False`` depending
    on whether *query* currently matches, and keeps it in sync as the viewport
    changes.  Useful for responsive logic driven from Python-generated signals.

    Args:
        signal: Signal name to bind (e.g. ``"isDark"``, ``"isWide"``).
        query: CSS media query string (with or without outer parentheses).

    Returns:
        ``{"data-match-media:{signal}": query}``

    Example::

        div(**match_media("isDark", "prefers-color-scheme: dark"))
        div(**match_media("isMobile", "(max-width: 768px)"))
    """
    return {f"data-match-media:{signal}": query}


def on_raf(expression: str) -> Dict[str, str]:
    """Run an expression on every ``requestAnimationFrame`` tick.

    Useful for smooth animations driven by signals without a polling interval.
    Note: this fires very frequently (~60 fps) — keep *expression* lightweight.

    Args:
        expression: Datastar expression to evaluate each frame.

    Returns:
        ``{"data-on-raf": expression}``

    Example::

        div(**on_raf("$angle = ($angle + 1) % 360"))
    """
    return {"data-on-raf": expression}


def on_resize(expression: str) -> Dict[str, str]:
    """Run an expression whenever the element's dimensions change.

    Uses a ``ResizeObserver`` under the hood.  Useful for responsive
    calculations that need the rendered element size rather than viewport size.

    Args:
        expression: Datastar expression to evaluate on resize.

    Returns:
        ``{"data-on-resize": expression}``

    Example::

        div(**on_resize("$panelWidth = $el.offsetWidth"))
    """
    return {"data-on-resize": expression}


def persist(
    key: Optional[str] = None,
    session: bool = False,
) -> Dict[str, str]:
    """Persist signals to ``localStorage`` (or ``sessionStorage``) across page loads.

    With no arguments, all signals are persisted to ``localStorage`` under a
    default key.  Provide *key* to control the storage key name; set *session*
    to use ``sessionStorage`` instead.

    Args:
        key: Optional storage key name. ``None`` uses Datastar's default.
        session: If ``True``, use ``sessionStorage`` instead of ``localStorage``.

    Returns:
        Attribute dict for ``data-persist`` or ``data-persist:{key}__session``.

    Examples::

        # Persist all signals (localStorage)
        div(**persist())

        # Named key in sessionStorage
        div(**persist(key="cart", session=True))
    """
    attr = "data-persist"
    if key:
        attr += f":{key}"
    if session:
        attr += "__session"
    return {attr: ""}


def query_string(
    filter: bool = False,
    history: bool = False,
) -> Dict[str, str]:
    """Sync signals to and from the URL query string.

    On page load, signals are populated from query parameters.  When signals
    change they are written back to the URL.  With ``filter=True`` only signals
    that already exist in the query string are synced; with ``history=True``
    updates create browser history entries instead of replacing the current one.

    Args:
        filter: Only sync signals present in the current query string.
        history: Push URL changes to browser history (enables back/forward).

    Returns:
        Attribute dict.

    Examples::

        # Sync all signals to query string (replaceState)
        div(**query_string())

        # Filter + push to history
        div(**query_string(filter=True, history=True))
    """
    attr = "data-query-string"
    if filter:
        attr += "__filter"
    if history:
        attr += "__history"
    return {attr: ""}


def replace_url(expression: str) -> Dict[str, str]:
    """Replace the browser URL without a page reload.

    Evaluates *expression* reactively and calls ``history.replaceState()``
    whenever the result changes.  For push-style (adds a history entry), use
    ``query_string(history=True)`` instead.

    Args:
        expression: Datastar expression yielding the new URL path string.

    Returns:
        ``{"data-replace-url": expression}``

    Example::

        div(**replace_url("`/items/${$currentPage}`"))
    """
    return {"data-replace-url": expression}


def rocket(component_name: str) -> Dict[str, str]:
    """Define a reactive web component from a ``<template>`` element.

    ``data-rocket:{component_name}`` converts a ``<template>`` into a custom
    HTML element with Datastar reactivity, scoped signals (``$$`` prefix),
    typed props via ``data-prop``, and automatic cleanup on removal.

    Args:
        component_name: Custom element name (kebab-case, must contain a hyphen,
            e.g. ``"my-counter"``, ``"user-card"``).

    Returns:
        ``{"data-rocket:{component_name}": ""}``

    Example::

        from gobstopper.html import template
        from gobstopper.html.datastar_pro import rocket

        template(
            **rocket("simple-counter"),
            **{"data-prop:count": "int (= 0)"},
        )[
            button(**{"data-on:click": "$$count--"})["−"],
            span(**{"data-text": "$$count"}),
            button(**{"data-on:click": "$$count++"})["+"],
        ]

    Note:
        Component signals use ``$$`` (not ``$``) to stay scoped per instance.
        Use as a custom element in HTML: ``<simple-counter></simple-counter>``.
    """
    if "-" not in component_name:
        raise ValueError(
            f"data-rocket component name must contain a hyphen (Web Components requirement): "
            f"got {component_name!r}"
        )
    return {f"data-rocket:{component_name}": ""}


def scroll_into_view(
    smooth: bool = False,
    focus: bool = False,
) -> Dict[str, str]:
    """Scroll the element into the viewport when it is rendered.

    Particularly useful with SSE-injected content — when Datastar patches new
    HTML into the DOM, any element with this attribute will scroll into view
    automatically.

    Args:
        smooth: Use smooth scrolling behaviour (``scroll-behavior: smooth``).
        focus: Also move keyboard focus to the element after scrolling.

    Returns:
        Attribute dict with appropriate ``__smooth`` / ``__focus`` modifiers.

    Examples::

        # Instant scroll
        div(**scroll_into_view())

        # Smooth scroll + focus (good for newly added form validation errors)
        p(".error", **scroll_into_view(smooth=True, focus=True))["Fix this field."]
    """
    attr = "data-scroll-into-view"
    if smooth:
        attr += "__smooth"
    if focus:
        attr += "__focus"
    return {attr: ""}


def view_transition(expression: str) -> Dict[str, str]:
    """Set the ``view-transition-name`` CSS property reactively.

    Binds the element's ``view-transition-name`` to a Datastar expression so
    it changes as signals change.  Works with the browser's View Transitions
    API for animated page-section transitions.

    Args:
        expression: Datastar expression resolving to a CSS ident string.

    Returns:
        ``{"data-view-transition": expression}``

    Example::

        div(**view_transition("'hero-' + $selectedId"))
    """
    return {"data-view-transition": expression}


# =============================================================================
# Pro Action Expression Helpers
#
# These return *strings* for use inside other attribute values, e.g.:
#   button(**on_click(clipboard("Hello!")))["Copy"]
# =============================================================================

def clipboard(text: str, is_base64: bool = False) -> str:
    """Generate a ``@clipboard()`` action expression (Pro).

    Copies *text* to the system clipboard when the surrounding action fires.
    When *is_base64* is ``True``, *text* is decoded from Base64 before copying
    — useful for safely embedding content with quotes or special characters in
    HTML attribute values.

    Args:
        text: The text to copy, or a Base64-encoded string.
        is_base64: If ``True``, decode *text* from Base64 before copying.

    Returns:
        ``@clipboard(...)`` expression string.

    Examples::

        # Plain copy
        button(**on_click(clipboard("Hello, world!")))["Copy"]

        # Base64-encoded (safe for HTML attributes with special characters)
        import base64
        encoded = base64.b64encode(b'She said "hello"').decode()
        button(**on_click(clipboard(encoded, is_base64=True)))["Copy quote"]
    """
    if is_base64:
        return f"@clipboard({json.dumps(text)}, true)"
    return f"@clipboard({json.dumps(text)})"


def fit(
    v: str,
    old_min: Union[float, int],
    old_max: Union[float, int],
    new_min: Union[float, int],
    new_max: Union[float, int],
    clamp: bool = False,
    round: bool = False,
) -> str:
    """Generate a ``@fit()`` linear-interpolation action expression (Pro).

    Maps a value from one numeric range to another.  Commonly used to convert
    slider positions to display values (e.g. 0–100 slider → 0–255 RGB).

    Args:
        v: Datastar expression for the input value (e.g. ``"$slider"``).
        old_min: Lower bound of the input range.
        old_max: Upper bound of the input range.
        new_min: Lower bound of the output range.
        new_max: Upper bound of the output range.
        clamp: Clamp the output to ``[new_min, new_max]``.
        round: Round the output to the nearest integer.

    Returns:
        ``@fit(...)`` expression string.

    Example::

        # Map a 0-100 range slider to RGB 0-255
        input_(
            type="range", min="0", max="100",
            **bind("sliderValue"),
        )
        div(**{"data-text": fit("$sliderValue", 0, 100, 0, 255, round=True)})
    """
    args = f"{v}, {old_min}, {old_max}, {new_min}, {new_max}"
    if clamp or round:
        args += f", {str(clamp).lower()}, {str(round).lower()}"
    return f"@fit({args})"


def intl(
    type: str,
    value: str,
    options: Optional[Dict[str, Any]] = None,
    locale: Optional[Union[str, list]] = None,
) -> str:
    """Generate an ``@intl()`` locale-aware formatting expression (Pro).

    Wraps JavaScript's ``Intl`` namespace for reactive locale-aware formatting
    of numbers, dates, lists, and more.

    Args:
        type: Intl formatter type.  One of: ``"number"``, ``"datetime"``,
            ``"pluralRules"``, ``"relativeTime"``, ``"list"``,
            ``"displayNames"``.
        value: Datastar expression for the value to format (e.g. ``"$price"``).
        options: Optional ``Intl`` options dict (e.g.
            ``{"style": "currency", "currency": "USD"}``).
        locale: BCP 47 locale string or list of strings (e.g. ``"de-AT"``).
            Defaults to the browser's locale.

    Returns:
        ``@intl(...)`` expression string.

    Examples::

        # USD currency
        span(**{"data-text": intl("number", "$price", {"style": "currency", "currency": "USD"})})

        # Long date in German
        span(**{"data-text": intl(
            "datetime", "$orderDate",
            {"weekday": "long", "year": "numeric", "month": "long", "day": "numeric"},
            "de-AT"
        )})

        # Pluralisation
        span(**{"data-text": intl("pluralRules", "$count")})
    """
    args = f"{json.dumps(type)}, {value}"
    if options is not None:
        args += f", {json.dumps(options)}"
        if locale is not None:
            args += f", {json.dumps(locale)}"
    elif locale is not None:
        # locale requires options to come first — use null
        args += f", null, {json.dumps(locale)}"
    return f"@intl({args})"
