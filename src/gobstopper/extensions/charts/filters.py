"""
Jinja2 template filters for chart manipulation.

This module provides template filters that can be used to modify
chart properties directly in templates. These filters are automatically
registered when ChartExtension is initialized.

Available Filters:
    chart_resize: Change chart dimensions
    chart_theme: Apply a different theme
    chart_to_json: Export chart configuration as JSON
    chart_animate: Configure chart animation

Note:
    These filters work with Jinja2 templates. For Tera templates,
    you should pre-render charts to HTML strings before passing
    them to templates.

Example:
    In a Jinja2 template::

        {{ chart | chart_resize('800px', '600px') | safe }}
        {{ chart | chart_animate(duration=2000) | safe }}
"""

import json
from typing import Any

from .builders import Chart


def chart_resize(chart: Chart, width: str = '100%', height: str = '500px') -> Chart:
    """
    Resize a chart.

    Usage:
        {{ chart | chart_resize('800px', '600px') | safe }}

    Args:
        chart: Chart object
        width: New width
        height: New height

    Returns:
        Modified chart
    """
    # Update internal chart dimensions
    if hasattr(chart._chart, 'width'):
        chart._chart.width = width
    if hasattr(chart._chart, 'height'):
        chart._chart.height = height

    return chart


def chart_theme(chart: Chart, theme: str) -> Chart:
    """
    Apply a theme to a chart.

    Usage:
        {{ chart | chart_theme('dark') | safe }}

    Args:
        chart: Chart object
        theme: Theme name

    Returns:
        Modified chart
    """
    # Note: pyecharts themes are set at initialization
    # This filter is limited in what it can change post-creation
    # Consider rebuilding the chart with the new theme instead
    return chart


def chart_to_json(chart: Chart, indent: int = 2) -> str:
    """
    Convert chart to JSON string.

    Usage:
        {{ chart | chart_to_json }}

    Args:
        chart: Chart object
        indent: JSON indentation

    Returns:
        JSON string of chart options
    """
    return json.dumps(chart.to_json(), indent=indent)


def chart_animate(chart: Chart, duration: int = 1000, easing: str = 'cubicOut') -> Chart:
    """
    Configure chart animation.

    Usage:
        {{ chart | chart_animate(2000) | safe }}

    Args:
        chart: Chart object
        duration: Animation duration in milliseconds
        easing: Easing function name

    Returns:
        Modified chart
    """
    # Set animation options on the underlying chart
    if hasattr(chart._chart, 'set_global_opts'):
        try:
            from pyecharts import options as opts
            chart._chart.set_global_opts(
                animation_opts=opts.AnimationOpts(
                    animation_duration=duration,
                    animation_easing=easing,
                )
            )
        except ImportError:
            pass

    return chart
