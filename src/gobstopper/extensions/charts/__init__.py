"""
Gobstopper Charts Extension

A powerful charting extension that integrates pyecharts with Gobstopper's template system.
Supports both standard and streaming template rendering.

Usage:
    from gobstopper import Gobstopper
    from gobstopper.extensions.charts import ChartExtension

    app = Gobstopper(__name__)
    charts = ChartExtension(app)

    @app.get('/dashboard')
    async def dashboard(request):
        chart = (charts.line()
            .add_xaxis(['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])
            .add_yaxis('Sales', [120, 200, 150, 80, 270])
            .set_title('Weekly Sales')
            .build())

        return await app.render_template('dashboard.html', chart=chart.html)
"""

from .extension import ChartExtension
from .builders import (
    Chart, ChartBuilder, LineChart, BarChart, PieChart, ScatterChart,
    CandlestickChart, TimelineChart
)
from .types import ChartTheme, CDNProvider

__all__ = [
    'ChartExtension',
    'Chart',
    'ChartBuilder',
    'LineChart',
    'BarChart',
    'PieChart',
    'ScatterChart',
    'CandlestickChart',
    'TimelineChart',
    'ChartTheme',
    'CDNProvider',
]

__version__ = '0.1.0'
