"""
Streaming template support for charts.

Provides utilities for rendering charts in Gobstopper's streaming templates,
where the container and script need to be rendered separately for
progressive page loading.

This module contains helpers for working with charts in streaming
contexts, ensuring proper ordering of DOM elements and JavaScript
initialization.
"""

from typing import AsyncIterator

from .builders import Chart


class StreamingChart:
    """
    Wrapper for rendering charts in streaming templates.

    Ensures proper ordering: container first, then script after DOM is ready.

    Usage:
        @app.get('/dashboard')
        async def dashboard(request):
            chart = charts.line()...build()
            streaming_chart = StreamingChart(chart)
            return await app.stream_template('dashboard.html', chart=streaming_chart)

    Template:
        {{ chart.container() | safe }}
        <!-- other content -->
        {{ chart.script() | safe }}
    """

    def __init__(self, chart: Chart):
        """
        Initialize streaming chart wrapper.

        Args:
            chart: Chart object to wrap
        """
        self._chart = chart

    # Methods (for calling with parentheses)
    def container(self) -> str:
        """
        Render the chart container div.

        This should be rendered first in the streaming template.

        Returns:
            HTML div with chart ID
        """
        return self._chart.render_container()

    def script(self) -> str:
        """
        Render the chart initialization script.

        This should be rendered after the container is in the DOM.

        Returns:
            JavaScript initialization code
        """
        return self._chart.render_script()

    @property
    def chart_id(self) -> str:
        """Get the chart ID."""
        return self._chart.chart_id

    @property
    def dependencies(self) -> list[str]:
        """Get script dependencies."""
        return self._chart.script_dependencies


async def stream_charts(*charts: Chart) -> AsyncIterator[str]:
    """
    Stream multiple charts efficiently.

    Yields containers first, then all scripts together.

    Usage:
        async for chunk in stream_charts(chart1, chart2, chart3):
            await websocket.send_text(chunk)

    Args:
        *charts: Chart objects to stream

    Yields:
        HTML/script chunks
    """
    # Yield dependencies once
    dependencies = set()
    for chart in charts:
        dependencies.update(chart.script_dependencies)

    for dep in dependencies:
        yield f'<script src="{dep}"></script>\n'

    # Yield all containers
    for chart in charts:
        yield chart.render_container()
        yield '\n'

    # Yield all scripts
    for chart in charts:
        yield chart.render_script()
        yield '\n'


def prepare_streaming_context(chart: Chart) -> dict:
    """
    Prepare a chart for streaming template context.

    Automatically wraps Chart objects in StreamingChart for convenience.

    Usage:
        context = prepare_streaming_context(chart)
        return await app.stream_template('page.html', **context)

    Args:
        chart: Chart to prepare

    Returns:
        Dictionary with streaming chart
    """
    return {'chart': StreamingChart(chart)}
