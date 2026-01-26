"""
Gobstopper Charts Extension - Demo Application

Demonstrates the charts extension with various chart types,
both standard and streaming template rendering.
"""

import asyncio
from datetime import datetime, timedelta
from gobstopper import Gobstopper
from gobstopper.http import JSONResponse
from gobstopper.extensions.charts import ChartExtension
from gobstopper.extensions.charts.streaming import StreamingChart

app = Gobstopper(__name__, debug=True)

# Initialize charts extension with default Tempest theme
charts = ChartExtension(app, theme='tempest')
app.init_templates("templates", use_rust=None, enable_streaming=True, enable_hot_reload=True)


# Sample data generators
def get_weekly_sales():
    """Get weekly sales data."""
    return {
        'days': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
        'sales': [120, 200, 150, 80, 270, 310, 260],
        'costs': [80, 120, 100, 60, 180, 200, 170],
    }


def get_product_distribution():
    """Get product category distribution."""
    return [
        ('Electronics', 450),
        ('Clothing', 320),
        ('Food', 280),
        ('Books', 150),
        ('Sports', 200),
    ]


def get_monthly_trends():
    """Get monthly trend data."""
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
    return {
        'months': months,
        'revenue': [45000, 52000, 48000, 61000, 58000, 67000],
        'profit': [12000, 15000, 13000, 18000, 17000, 21000],
        'customers': [1200, 1350, 1280, 1520, 1480, 1680],
    }


def get_scatter_data():
    """Get scatter plot data."""
    import random
    return [
        [random.randint(0, 100), random.randint(0, 100)]
        for _ in range(50)
    ]


def get_candlestick_data():
    """Get candlestick (stock) data."""
    # Sample stock data: [open, close, low, high]
    return {
        'dates': ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2024-06'],
        'values': [
            [20, 34, 10, 38],  # Open, Close, Low, High
            [40, 35, 30, 50],
            [31, 38, 33, 44],
            [38, 15, 15, 48],
            [15, 25, 12, 35],
            [25, 35, 20, 40],
        ],
    }


# Routes

@app.get('/')
async def index(request):
    """Homepage with chart examples."""
    return await app.render_template('charts_index.html')


@app.get('/dashboard')
async def dashboard(request):
    """Standard dashboard with multiple charts."""
    sales_data = get_weekly_sales()
    product_data = get_product_distribution()
    trend_data = get_monthly_trends()

    # Create line chart for weekly sales
    sales_chart = (charts.line()
        .add_xaxis(sales_data['days'])
        .add_yaxis('Sales', sales_data['sales'], smooth=True, area=True)
        .add_yaxis('Costs', sales_data['costs'], smooth=True)
        .set_title('Weekly Sales vs Costs', 'Last 7 days performance')
        .build())

    # Create pie chart for product distribution
    product_chart = (charts.pie()
        .add_data(product_data)
        .set_title('Product Distribution', 'Sales by category')
        .set_radius(['40%', '70%'])  # Donut chart
        .build())

    # Create bar chart for monthly trends
    trend_chart = (charts.bar()
        .add_xaxis(trend_data['months'])
        .add_yaxis('Revenue', trend_data['revenue'])
        .add_yaxis('Profit', trend_data['profit'])
        .set_title('Monthly Trends', '6-month overview')
        .build())

    return await app.render_template('charts_dashboard.html',
        sales_chart=sales_chart.html,
        product_chart=product_chart.html,
        trend_chart=trend_chart.html,
    )


@app.get('/streaming')
async def streaming_dashboard(request):
    """Streaming dashboard with progressive chart loading."""
    sales_data = get_weekly_sales()
    product_data = get_product_distribution()
    trend_data = get_monthly_trends()

    # Create charts
    sales_chart = (charts.line()
        .add_xaxis(sales_data['days'])
        .add_yaxis('Sales', sales_data['sales'], smooth=True)
        .set_title('Weekly Sales')
        .build())

    product_chart = (charts.pie()
        .add_data(product_data)
        .set_title('Product Distribution')
        .build())

    trend_chart = (charts.bar()
        .add_xaxis(trend_data['months'])
        .add_yaxis('Revenue', trend_data['revenue'])
        .set_title('Monthly Revenue')
        .build())

    result = await app.render_template('charts_streaming.html',
        sales_chart_container=sales_chart.container,
        sales_chart_script=sales_chart.script,
        product_chart_container=product_chart.container,
        product_chart_script=product_chart.script,
        trend_chart_container=trend_chart.container,
        trend_chart_script=trend_chart.script,
                                       streaming=True
    )
    if hasattr(result, '__aiter__'):
        chunks = []
        async for chunk in result:
            chunks.append(chunk)
        result = ''.join(chunks)
        request.logger.info(f"✅ Streamed {len(chunks)} chunks")
    return result


@app.get('/api/live-data')
async def live_data(request):
    """API endpoint for live data updates."""
    import random

    # Generate random data point
    now = datetime.now()
    return JSONResponse({
        'timestamp': now.strftime('%H:%M:%S'),
        'value': random.randint(50, 200),
    })


@app.get('/realtime')
async def realtime(request):
    """Real-time chart demo (client-side updates)."""
    # Create empty chart that will be updated via JavaScript
    initial_data = {
        'times': [],
        'values': [],
    }

    chart = (charts.line()
        .add_xaxis(initial_data['times'])
        .add_yaxis('Live Data', initial_data['values'])
        .set_title('Real-time Data Stream', 'Updates every second')
        .build())

    return await app.render_template('charts_realtime.html', chart=chart)


@app.get('/gallery')
async def gallery(request):
    """Chart type gallery."""
    # Line chart
    line_chart = (charts.line()
        .add_xaxis(['A', 'B', 'C', 'D', 'E'])
        .add_yaxis('Series 1', [10, 20, 15, 30, 25], smooth=True)
        .set_title('Line Chart')
        .build())

    # Bar chart
    bar_chart = (charts.bar()
        .add_xaxis(['Q1', 'Q2', 'Q3', 'Q4'])
        .add_yaxis('Revenue', [45, 52, 48, 61])
        .set_title('Bar Chart')
        .build())

    # Stacked bar chart
    stacked_bar = (charts.bar()
        .add_xaxis(['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])
        .add_yaxis('Product A', [20, 25, 22, 28, 30], stack='total')
        .add_yaxis('Product B', [15, 18, 20, 17, 22], stack='total')
        .add_yaxis('Product C', [10, 12, 15, 13, 18], stack='total')
        .set_title('Stacked Bar Chart')
        .set_stack('total')
        .build())

    # Pie chart
    pie_chart = (charts.pie()
        .add_data([('A', 335), ('B', 234), ('C', 548), ('D', 135)])
        .set_title('Pie Chart')
        .build())

    # Donut chart
    donut_chart = (charts.pie()
        .add_data([('Direct', 335), ('Email', 310), ('Ads', 234), ('Video', 135), ('Search', 548)])
        .set_title('Donut Chart')
        .set_radius(['40%', '70%'])
        .build())

    # Scatter plot - scatter needs xaxis defined
    scatter_data = get_scatter_data()
    x_values = [point[0] for point in scatter_data]
    y_values = [point[1] for point in scatter_data]
    scatter_chart = (charts.scatter()
        .add_xaxis(x_values)
        .add_yaxis('Series', y_values)
        .set_title('Scatter Plot')
        .build())

    # Candlestick chart
    candlestick_data = get_candlestick_data()
    candlestick_chart = (charts.candlestick()
        .add_xaxis(candlestick_data['dates'])
        .add_yaxis('Stock', candlestick_data['values'])
        .set_title('Candlestick Chart')
        .build())

    return await app.render_template('charts_gallery.html',
        line_chart=line_chart.html,
        bar_chart=bar_chart.html,
        stacked_bar=stacked_bar.html,
        pie_chart=pie_chart.html,
        donut_chart=donut_chart.html,
        scatter_chart=scatter_chart.html,
        candlestick_chart=candlestick_chart.html,
    )


@app.get('/themes')
async def themes_demo(request):
    """Theme comparison demo."""
    data = get_weekly_sales()

    # Same chart with different themes
    light_chart = (charts.line(theme='tempest')
        .add_xaxis(data['days'])
        .add_yaxis('Sales', data['sales'], smooth=True)
        .set_title('Tempest Light Theme')
        .build())

    dark_chart = (charts.line(theme='tempest-dark')
        .add_xaxis(data['days'])
        .add_yaxis('Sales', data['sales'], smooth=True)
        .set_title('Tempest Dark Theme')
        .build())

    vintage_chart = (charts.line(theme='vintage')
        .add_xaxis(data['days'])
        .add_yaxis('Sales', data['sales'], smooth=True)
        .set_title('Vintage Theme')
        .build())

    return await app.render_template('charts_themes.html',
        light_chart=light_chart.html,
        dark_chart=dark_chart.html,
        vintage_chart=vintage_chart.html,
    )


if __name__ == '__main__':
    print("=" * 60)
    print("📊 Tempest Charts Extension - Demo Application")
    print("=" * 60)
    print("\nAvailable Routes:")
    print("  • http://localhost:8000/              - Homepage")
    print("  • http://localhost:8000/dashboard     - Standard dashboard")
    print("  • http://localhost:8000/streaming     - Streaming dashboard")
    print("  • http://localhost:8000/realtime      - Real-time updates")
    print("  • http://localhost:8000/gallery       - Chart type gallery")
    print("  • http://localhost:8000/themes        - Theme comparison")
    print("\n🚀 Run with:")
    print("  granian --interface rsgi --reload examples/charts_demo:app")
    print("=" * 60)
