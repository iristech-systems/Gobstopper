"""
Fluent chart builders for creating beautiful, interactive charts.

This module provides a chainable API for constructing various chart types
using pyecharts. All builders follow the Builder pattern, allowing you to
chain method calls to configure your charts before building the final Chart object.

Supported Chart Types:
    - LineChart: Line charts with smooth curves, area fills, and stacking
    - BarChart: Vertical bar charts with grouping and stacking support
    - PieChart: Pie and donut charts with customizable radius
    - ScatterChart: Scatter plots for correlation visualization
    - CandlestickChart: Financial charts for OHLC stock data
    - TimelineChart: Animated charts across different time periods

Example:
    Basic line chart::

        from gobstopper.extensions.charts import ChartExtension

        charts = ChartExtension(app)
        chart = (charts.line()
            .add_xaxis(['Mon', 'Tue', 'Wed'])
            .add_yaxis('Sales', [100, 200, 150], smooth=True)
            .set_title('Weekly Sales')
            .build())

All chart builders return a Chart object that can be rendered to HTML
for use in Gobstopper templates.
"""

import uuid
from typing import Any, Self
from abc import ABC, abstractmethod

try:
    from pyecharts import options as opts
    from pyecharts.charts import (
        Line, Bar, Pie, Scatter, Funnel, Gauge, Radar, HeatMap,
        Candlestick, Timeline
    )
    from pyecharts.globals import ThemeType
    PYECHARTS_AVAILABLE = True
except ImportError:
    PYECHARTS_AVAILABLE = False
    # Create dummy classes for type hints
    Line = Bar = Pie = Scatter = Funnel = Gauge = Radar = HeatMap = None
    Candlestick = Timeline = None
    opts = None
    ThemeType = None

from .themes import get_theme


class Chart:
    """
    A rendered chart ready for template rendering.

    This class wraps a pyecharts chart object and provides multiple rendering modes
    optimized for Gobstopper templates. It supports both standard templates (Jinja2/Tera)
    and streaming templates with progressive loading.

    Attributes:
        chart_id (str): Unique identifier for the chart
        html (str): Full HTML embed with chart and scripts (property)
        container (str): Just the chart container div (property)
        script (str): Just the initialization script (property)

    Template Usage:
        Standard templates::

            {{ chart.html | safe }}

        Streaming templates::

            {{ chart.container | safe }}
            <!-- other content -->
            {{ chart.script | safe }}

    The Chart object automatically handles:
        - Unique chart IDs for multiple charts on one page
        - JavaScript dependency management
        - Responsive chart resizing
        - Template engine compatibility (Jinja2 and Tera)
    """

    def __init__(self, chart: Any, chart_id: str | None = None):
        """
        Initialize a chart.

        Args:
            chart: The pyecharts chart object
            chart_id: Unique ID for the chart (generated if not provided)
        """
        self._chart = chart
        self._chart_id = chart_id or f"chart_{uuid.uuid4().hex[:8]}"
        self._dependencies_loaded = False

    @property
    def chart_id(self) -> str:
        """Get the unique chart ID."""
        return self._chart_id

    @property
    def script_dependencies(self) -> list[str]:
        """Get list of required script URLs."""
        # ECharts core is always required
        return [
            'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'
        ]

    # Template-friendly properties (work with Tera - no parentheses needed)
    @property
    def html(self) -> str:
        """Alias for render_embed() - works with Tera templates."""
        return self.render_embed()

    @property
    def container(self) -> str:
        """Alias for render_container() - works with Tera templates."""
        return self.render_container()

    @property
    def script(self) -> str:
        """Alias for render_script() - works with Tera templates."""
        return self.render_script()

    def render_embed(self) -> str:
        """
        Render chart as embeddable HTML (without <html> wrapper).

        Returns:
            HTML string with chart container and initialization script
        """
        if not PYECHARTS_AVAILABLE:
            return '<div style="color: red;">pyecharts not installed. Install with: pip install wopr[charts]</div>'

        # Get the chart HTML
        html = self._chart.render_embed()
        return html

    def render_container(self) -> str:
        """
        Render only the chart container div (for streaming templates).

        Returns:
            HTML div element with chart ID
        """
        if not PYECHARTS_AVAILABLE:
            return '<div style="color: red;">pyecharts not installed.</div>'

        # Extract chart dimensions from options
        width = getattr(self._chart, 'width', '100%')
        height = getattr(self._chart, 'height', '500px')

        return f'<div id="{self._chart_id}" style="width: {width}; height: {height};"></div>'

    def render_script(self) -> str:
        """
        Render the chart initialization script (for streaming templates).

        Returns:
            JavaScript code to initialize the chart
        """
        if not PYECHARTS_AVAILABLE:
            return ''

        # Get chart options as JSON
        options = self._chart.get_options()

        script = f"""
<script type="text/javascript">
    (function() {{
        var chartDom = document.getElementById('{self._chart_id}');
        if (!chartDom) {{
            console.error('Chart container not found: {self._chart_id}');
            return;
        }}
        var chart = echarts.init(chartDom);
        var option = {options};
        chart.setOption(option);

        // Responsive resize
        window.addEventListener('resize', function() {{
            chart.resize();
        }});
    }})();
</script>
"""
        return script

    def to_json(self) -> dict:
        """
        Export chart options as JSON.

        Returns:
            Chart configuration as dictionary
        """
        if not PYECHARTS_AVAILABLE:
            return {}
        return self._chart.get_options()

    def render_notebook(self) -> str:
        """
        Render for Jupyter notebooks.

        Returns:
            HTML suitable for notebook display
        """
        if not PYECHARTS_AVAILABLE:
            return ''
        return self._chart.render_notebook()


class ChartBuilder(ABC):
    """
    Base class for all chart builders.

    This abstract base class implements the Builder pattern, providing
    common functionality for all chart types including title, legend,
    tooltip, and toolbox configuration.

    All chart builders follow a fluent interface pattern where methods
    return `self` to allow chaining. The final `.build()` method creates
    the Chart object.

    Common Methods:
        - set_title(): Configure chart title and subtitle
        - set_legend(): Configure legend position and style
        - set_tooltip(): Configure tooltip trigger and format
        - set_toolbox(): Add save, zoom, and other tools
        - build(): Create the final Chart object

    Subclasses must implement:
        - _create_chart(): Build the underlying pyecharts chart

    Note:
        This class should not be instantiated directly. Use specific
        chart builder classes like LineChart, BarChart, etc.
    """

    def __init__(self, width: str = '100%', height: str = '500px', theme: str = 'tempest'):
        """
        Initialize chart builder.

        Args:
            width: Chart width (e.g., '800px', '100%')
            height: Chart height (e.g., '500px', '400px')
            theme: Theme name
        """
        if not PYECHARTS_AVAILABLE:
            raise ImportError(
                'pyecharts is required for charts extension. '
                'Install with: pip install wopr[charts]'
            )

        self._width = width
        self._height = height
        self._theme = theme
        self._chart_id = f"chart_{uuid.uuid4().hex[:8]}"
        self._title: str | None = None
        self._subtitle: str | None = None
        self._legend_opts: dict[str, Any] | None = None
        self._tooltip_opts: dict[str, Any] | None = None
        self._toolbox_opts: dict[str, Any] | None = None

    @abstractmethod
    def _create_chart(self) -> Any:
        """Create the underlying pyecharts chart object."""
        pass

    def set_title(self, title: str, subtitle: str | None = None, **kwargs) -> Self:
        """
        Set chart title.

        Args:
            title: Main title text
            subtitle: Subtitle text
            **kwargs: Additional title options

        Returns:
            Self for chaining
        """
        self._title = title
        self._subtitle = subtitle
        return self

    def set_legend(self, **kwargs) -> Self:
        """
        Configure legend.

        Args:
            **kwargs: Legend options (pos_left, pos_top, orient, etc.)

        Returns:
            Self for chaining
        """
        self._legend_opts = kwargs
        return self

    def set_tooltip(self, trigger: str = 'axis', **kwargs) -> Self:
        """
        Configure tooltip.

        Args:
            trigger: Trigger type ('axis', 'item', 'none')
            **kwargs: Additional tooltip options

        Returns:
            Self for chaining
        """
        self._tooltip_opts = {'trigger': trigger, **kwargs}
        return self

    def set_toolbox(self, **kwargs) -> Self:
        """
        Configure toolbox (save, zoom, etc.).

        Args:
            **kwargs: Toolbox options

        Returns:
            Self for chaining
        """
        self._toolbox_opts = kwargs
        return self

    def _apply_common_options(self, chart: Any) -> Any:
        """Apply common options to chart."""
        # Set title
        if self._title:
            chart.set_global_opts(
                title_opts=opts.TitleOpts(
                    title=self._title,
                    subtitle=self._subtitle or '',
                )
            )

        # Set legend
        if self._legend_opts:
            chart.set_global_opts(legend_opts=opts.LegendOpts(**self._legend_opts))

        # Set tooltip
        if self._tooltip_opts:
            chart.set_global_opts(tooltip_opts=opts.TooltipOpts(**self._tooltip_opts))
        else:
            # Default tooltip
            chart.set_global_opts(tooltip_opts=opts.TooltipOpts(trigger='axis'))

        # Set toolbox
        if self._toolbox_opts:
            chart.set_global_opts(toolbox_opts=opts.ToolboxOpts(**self._toolbox_opts))

        return chart

    def build(self) -> Chart:
        """
        Build the final Chart object.

        Returns:
            Chart ready for rendering
        """
        chart = self._create_chart()
        chart = self._apply_common_options(chart)
        return Chart(chart, self._chart_id)


class LineChart(ChartBuilder):
    """Builder for line charts."""

    def __init__(self, width: str = '100%', height: str = '500px', theme: str = 'tempest'):
        super().__init__(width, height, theme)
        self._xaxis_data: list = []
        self._series: list[dict[str, Any]] = []
        self._is_smooth = False
        self._is_area = False

    def add_xaxis(self, data: list) -> Self:
        """
        Add X-axis data.

        Args:
            data: List of X-axis labels/values

        Returns:
            Self for chaining
        """
        self._xaxis_data = data
        return self

    def add_yaxis(
        self,
        name: str,
        data: list,
        smooth: bool | None = None,
        area: bool = False,
        **kwargs
    ) -> Self:
        """
        Add Y-axis series.

        Args:
            name: Series name
            data: Series data points
            smooth: Enable smooth curves (overrides chart-level setting)
            area: Fill area under line
            **kwargs: Additional series options

        Returns:
            Self for chaining
        """
        self._series.append({
            'name': name,
            'data': data,
            'smooth': smooth if smooth is not None else self._is_smooth,
            'area': area or self._is_area,
            'kwargs': kwargs,
        })
        return self

    def set_smooth(self, smooth: bool = True) -> Self:
        """
        Enable smooth curves for all series.

        Args:
            smooth: Whether to smooth lines

        Returns:
            Self for chaining
        """
        self._is_smooth = smooth
        return self

    def set_area(self, area: bool = True) -> Self:
        """
        Fill area under lines.

        Args:
            area: Whether to fill area

        Returns:
            Self for chaining
        """
        self._is_area = area
        return self

    def _create_chart(self) -> Any:
        """Create line chart."""
        # Determine theme - use 'white' as base for custom themes
        custom_theme = get_theme(self._theme)
        init_opts = opts.InitOpts(
            width=self._width,
            height=self._height,
            theme='white' if custom_theme else self._theme,
        )

        chart = Line(init_opts=init_opts)
        chart.add_xaxis(self._xaxis_data)

        # Add series
        for series in self._series:
            area_opts = opts.AreaStyleOpts() if series['area'] else None
            chart.add_yaxis(
                series_name=series['name'],
                y_axis=series['data'],
                is_smooth=series['smooth'],
                areastyle_opts=area_opts,
                **series['kwargs'],
            )

        return chart


class BarChart(ChartBuilder):
    """Builder for bar charts."""

    def __init__(self, width: str = '100%', height: str = '500px', theme: str = 'tempest'):
        super().__init__(width, height, theme)
        self._xaxis_data: list = []
        self._series: list[dict[str, Any]] = []
        self._stack: str | None = None

    def add_xaxis(self, data: list) -> Self:
        """
        Add X-axis categories.

        Args:
            data: List of category labels

        Returns:
            Self for chaining
        """
        self._xaxis_data = data
        return self

    def add_yaxis(self, name: str, data: list, stack: str | None = None, **kwargs) -> Self:
        """
        Add bar series.

        Args:
            name: Series name
            data: Series data values
            stack: Stack group name (for stacked bars)
            **kwargs: Additional series options

        Returns:
            Self for chaining
        """
        self._series.append({
            'name': name,
            'data': data,
            'stack': stack or self._stack,
            'kwargs': kwargs,
        })
        return self

    def set_stack(self, stack: str) -> Self:
        """
        Enable stacking for all series.

        Args:
            stack: Stack group name

        Returns:
            Self for chaining
        """
        self._stack = stack
        return self

    def _create_chart(self) -> Any:
        """Create bar chart."""
        custom_theme = get_theme(self._theme)
        init_opts = opts.InitOpts(
            width=self._width,
            height=self._height,
            theme="white" if custom_theme else self._theme,  # Can't be None!
        )

        chart = Bar(init_opts=init_opts)
        chart.add_xaxis(self._xaxis_data)

        # Add series
        for series in self._series:
            chart.add_yaxis(
                series_name=series['name'],
                y_axis=series['data'],
                stack=series['stack'],
                **series['kwargs'],
            )

        return chart


class PieChart(ChartBuilder):
    """Builder for pie charts."""

    def __init__(self, width: str = '100%', height: str = '500px', theme: str = 'tempest'):
        super().__init__(width, height, theme)
        self._data: list[tuple[str, float]] = []
        self._radius: str | list = '60%'
        self._rosetype: str | None = None

    def add_data(self, data: list[tuple[str, float]], **kwargs) -> Self:
        """
        Add pie data.

        Args:
            data: List of (name, value) tuples
            **kwargs: Additional data options

        Returns:
            Self for chaining
        """
        self._data = data
        return self

    def set_radius(self, radius: str | list) -> Self:
        """
        Set pie radius.

        Args:
            radius: Radius as string ('50%') or list (['40%', '70%'] for donut)

        Returns:
            Self for chaining
        """
        self._radius = radius
        return self

    def set_rosetype(self, rosetype: str = 'radius') -> Self:
        """
        Enable rose diagram.

        Args:
            rosetype: Rose type ('radius' or 'area')

        Returns:
            Self for chaining
        """
        self._rosetype = rosetype
        return self

    def _create_chart(self) -> Any:
        """Create pie chart."""
        custom_theme = get_theme(self._theme)
        init_opts = opts.InitOpts(
            width=self._width,
            height=self._height,
            theme="white" if custom_theme else self._theme,  # Can't be None!
        )

        chart = Pie(init_opts=init_opts)
        chart.add(
            series_name='',
            data_pair=self._data,
            radius=self._radius,
            rosetype=self._rosetype,
        )

        return chart


class ScatterChart(ChartBuilder):
    """Builder for scatter plots."""

    def __init__(self, width: str = '100%', height: str = '500px', theme: str = 'tempest'):
        super().__init__(width, height, theme)
        self._xaxis_data: list = []
        self._series: list[dict[str, Any]] = []

    def add_xaxis(self, data: list) -> Self:
        """
        Add X-axis data.

        Args:
            data: X-axis values

        Returns:
            Self for chaining
        """
        self._xaxis_data = data
        return self

    def add_yaxis(self, name: str, data: list, **kwargs) -> Self:
        """
        Add scatter series.

        Args:
            name: Series name
            data: Y-axis values (or list of [x, y] pairs)
            **kwargs: Additional series options

        Returns:
            Self for chaining
        """
        self._series.append({
            'name': name,
            'data': data,
            'kwargs': kwargs,
        })
        return self

    def _create_chart(self) -> Any:
        """Create scatter chart."""
        custom_theme = get_theme(self._theme)
        init_opts = opts.InitOpts(
            width=self._width,
            height=self._height,
            theme='white' if custom_theme else self._theme,  # Can't be None!
        )

        chart = Scatter(init_opts=init_opts)

        # Scatter REQUIRES add_xaxis() to be called first
        if self._xaxis_data:
            chart.add_xaxis(self._xaxis_data)

        # Add series
        for series in self._series:
            chart.add_yaxis(
                series_name=series['name'],
                y_axis=series['data'],
                **series['kwargs'],
            )

        return chart


class CandlestickChart(ChartBuilder):
    """Builder for candlestick (K-line) charts - commonly used for stock data."""

    def __init__(self, width: str = '100%', height: str = '500px', theme: str = 'tempest'):
        super().__init__(width, height, theme)
        self._xaxis_data: list = []
        self._yaxis_data: list = []  # List of [open, close, low, high]

    def add_xaxis(self, data: list) -> Self:
        """
        Add X-axis data (typically dates/timestamps).

        Args:
            data: List of date/time labels

        Returns:
            Self for chaining
        """
        self._xaxis_data = data
        return self

    def add_yaxis(self, name: str, data: list[list], **kwargs) -> Self:
        """
        Add candlestick data.

        Args:
            name: Series name
            data: List of [open, close, low, high] values for each candle
            **kwargs: Additional series options

        Returns:
            Self for chaining

        Example:
            .add_yaxis('Stock', [
                [20, 34, 10, 38],  # open, close, low, high
                [40, 35, 30, 50],
            ])
        """
        self._yaxis_data = data
        return self

    def _create_chart(self) -> Any:
        """Create candlestick chart."""
        custom_theme = get_theme(self._theme)
        init_opts = opts.InitOpts(
            width=self._width,
            height=self._height,
            theme='white' if custom_theme else self._theme,
        )

        chart = Candlestick(init_opts=init_opts)
        chart.add_xaxis(self._xaxis_data)
        chart.add_yaxis('', self._yaxis_data)

        return chart


class TimelineChart(ChartBuilder):
    """
    Builder for timeline charts - allows animating through different time periods.
    
    Timeline charts are special - they contain multiple charts that can be
    navigated through a timeline slider.
    """

    def __init__(self, width: str = '100%', height: str = '500px', theme: str = 'tempest'):
        super().__init__(width, height, theme)
        self._charts: dict[str, Any] = {}  # Timeline label -> Chart mapping
        
    def add_chart(self, time_label: str, chart: Any) -> Self:
        """
        Add a chart for a specific time point.

        Args:
            time_label: Label for this time point (e.g., '2020', 'Q1')
            chart: A pyecharts chart object (Bar, Line, etc.)

        Returns:
            Self for chaining

        Example:
            timeline = charts.timeline()
            timeline.add_chart('2020', bar_chart_2020)
            timeline.add_chart('2021', bar_chart_2021)
        """
        self._charts[time_label] = chart
        return self

    def _create_chart(self) -> Any:
        """Create timeline chart."""
        custom_theme = get_theme(self._theme)
        init_opts = opts.InitOpts(
            width=self._width,
            height=self._height,
            theme='white' if custom_theme else self._theme,
        )

        timeline = Timeline(init_opts=init_opts)
        
        # Add charts in order
        for time_label, chart in self._charts.items():
            timeline.add(chart, time_label)

        return timeline
