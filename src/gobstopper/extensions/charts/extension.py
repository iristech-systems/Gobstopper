"""
Main ChartExtension class for Gobstopper charts integration.

This module provides the primary interface for creating interactive charts
in Gobstopper applications using pyecharts.
"""

from typing import TYPE_CHECKING, Any

from .builders import LineChart, BarChart, PieChart, ScatterChart
from .themes import register_tempest_themes
from .types import CDNProvider, ChartTheme

if TYPE_CHECKING:
    from gobstopper.core.app import Gobstopper


class ChartExtension:
    """
    Charts extension for Gobstopper framework.

    Integrates pyecharts with Gobstopper's template system, providing
    a fluent API for creating beautiful, interactive charts with
    support for both standard and streaming template rendering.

    Attributes:
        app: The Gobstopper application instance
        cdn: CDN provider for ECharts JavaScript library
        default_theme: Default theme for all charts
        default_width: Default width for charts
        default_height: Default height for charts

    Example:
        Basic usage::

            from gobstopper import Gobstopper
            from gobstopper.extensions.charts import ChartExtension

            app = Gobstopper(__name__)
            charts = ChartExtension(app)

            @app.get('/dashboard')
            async def dashboard(request):
                chart = (charts.line()
                    .add_xaxis(['Mon', 'Tue', 'Wed'])
                    .add_yaxis('Sales', [120, 200, 150])
                    .set_title('Weekly Sales')
                    .build())
                return await app.render_template('dashboard.html',
                                                chart=chart.html)

        With custom theme and dimensions::

            charts = ChartExtension(
                app,
                theme='dark',
                default_width='800px',
                default_height='400px'
            )
    """

    def __init__(
        self,
        app: 'Gobstopper',
        cdn: CDNProvider = 'jsdelivr',
        theme: ChartTheme = 'tempest',
        default_width: str = '100%',
        default_height: str = '500px',
    ):
        """
        Initialize charts extension.

        Args:
            app: Gobstopper application instance
            cdn: CDN provider for ECharts scripts ('jsdelivr', 'cdnjs', 'unpkg', or 'local')
            theme: Default theme for charts ('tempest', 'tempest-dark', or any pyecharts theme)
            default_width: Default chart width (e.g., '100%', '800px')
            default_height: Default chart height (e.g., '500px', '400px')
        """
        self.app = app
        self.cdn = cdn
        self.default_theme = theme
        self.default_width = default_width
        self.default_height = default_height

        # Register Tempest themes with pyecharts
        register_tempest_themes()

        # Register Jinja2 filters if template engine available
        self._register_template_filters()

    def _register_template_filters(self) -> None:
        """Register Jinja2 template filters for charts."""
        if not hasattr(self.app, 'template_engine') or not self.app.template_engine:
            return

        from .filters import chart_resize, chart_theme, chart_to_json

        self.app.template_engine.env.filters['chart_resize'] = chart_resize
        self.app.template_engine.env.filters['chart_theme'] = chart_theme
        self.app.template_engine.env.filters['chart_to_json'] = chart_to_json

    def line(
        self,
        width: str | None = None,
        height: str | None = None,
        theme: ChartTheme | None = None,
    ) -> LineChart:
        """
        Create a line chart builder.

        Args:
            width: Chart width (defaults to extension default)
            height: Chart height (defaults to extension default)
            theme: Chart theme (defaults to extension default)

        Returns:
            LineChart builder for chaining
        """
        return LineChart(
            width=width or self.default_width,
            height=height or self.default_height,
            theme=theme or self.default_theme,
        )

    def bar(
        self,
        width: str | None = None,
        height: str | None = None,
        theme: ChartTheme | None = None,
    ) -> BarChart:
        """
        Create a bar chart builder.

        Args:
            width: Chart width (defaults to extension default)
            height: Chart height (defaults to extension default)
            theme: Chart theme (defaults to extension default)

        Returns:
            BarChart builder for chaining
        """
        return BarChart(
            width=width or self.default_width,
            height=height or self.default_height,
            theme=theme or self.default_theme,
        )

    def pie(
        self,
        width: str | None = None,
        height: str | None = None,
        theme: ChartTheme | None = None,
    ) -> PieChart:
        """
        Create a pie chart builder.

        Args:
            width: Chart width (defaults to extension default)
            height: Chart height (defaults to extension default)
            theme: Chart theme (defaults to extension default)

        Returns:
            PieChart builder for chaining
        """
        return PieChart(
            width=width or self.default_width,
            height=height or self.default_height,
            theme=theme or self.default_theme,
        )

    def scatter(
        self,
        width: str | None = None,
        height: str | None = None,
        theme: ChartTheme | None = None,
    ) -> ScatterChart:
        """
        Create a scatter plot builder.

        Args:
            width: Chart width (defaults to extension default)
            height: Chart height (defaults to extension default)
            theme: Chart theme (defaults to extension default)

        Returns:
            ScatterChart builder for chaining
        """
        return ScatterChart(
            width=width or self.default_width,
            height=height or self.default_height,
            theme=theme or self.default_theme,
        )

    def get_cdn_url(self) -> str:
        """
        Get the CDN URL for ECharts library.

        Returns:
            CDN URL based on configured provider
        """
        urls = {
            'jsdelivr': 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js',
            'cdnjs': 'https://cdnjs.cloudflare.com/ajax/libs/echarts/5.4.3/echarts.min.js',
            'unpkg': 'https://unpkg.com/echarts@5/dist/echarts.min.js',
            'local': '/static/echarts.min.js',  # User must provide
        }
        return urls.get(self.cdn, urls['jsdelivr'])

    def candlestick(
        self,
        width: str | None = None,
        height: str | None = None,
        theme: ChartTheme | None = None,
    ) -> 'CandlestickChart':
        """
        Create a candlestick (K-line) chart builder.

        Args:
            width: Chart width (defaults to extension default)
            height: Chart height (defaults to extension default)
            theme: Chart theme (defaults to extension default)

        Returns:
            CandlestickChart builder for chaining
        """
        from .builders import CandlestickChart
        return CandlestickChart(
            width=width or self.default_width,
            height=height or self.default_height,
            theme=theme or self.default_theme,
        )

    def timeline(
        self,
        width: str | None = None,
        height: str | None = None,
        theme: ChartTheme | None = None,
    ) -> 'TimelineChart':
        """
        Create a timeline chart builder.

        Timeline charts allow animating through different time periods.

        Args:
            width: Chart width (defaults to extension default)
            height: Chart height (defaults to extension default)
            theme: Chart theme (defaults to extension default)

        Returns:
            TimelineChart builder for chaining
        """
        from .builders import TimelineChart
        return TimelineChart(
            width=width or self.default_width,
            height=height or self.default_height,
            theme=theme or self.default_theme,
        )
