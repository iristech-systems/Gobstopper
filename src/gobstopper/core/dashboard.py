
from ..core.blueprint import Blueprint
from ..http.request import Request
from ..http.response import JSONResponse, Response
from pyecharts.charts import Gauge
from pyecharts import options as opts
from pyecharts.globals import CurrentConfig
import time
import os
import psutil
import datetime
import aiohttp
import asyncio
import json
import platform
from ..extensions.charts.builders import LineChart

# Use jsdelivr to match our CSP policy
CurrentConfig.ONLINE_HOST = "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/"

dashboard = Blueprint("dashboard", url_prefix="/_gobstopper")

DASHBOARD_TOKEN = os.getenv("GOBSTOPPER_DASHBOARD_TOKEN")

def check_auth(request: Request):
    """Check if the request is authorized via token."""
    # If a token is configured, enforce it PRIORITIZED over debug mode
    # This matches user expectation: setting a token = enforcing security
    if DASHBOARD_TOKEN:
        val = request.args.get("token")
        if not val:
            return False
            
        token = val[0] if isinstance(val, list) else val
        return token == DASHBOARD_TOKEN

    # Always allow in debug mode for developer convenience IF no token is set
    if getattr(request.app, 'debug', False):
        return True

    # Per user request: If no token is configured and not in debug mode, 
    # the dashboard is disabled/hidden for security.
    return False

def get_base_html(token_param=""):
    """Generate the dashboard HTML with chart options injected."""
    
    # Generate CPU Gauge Options using Pyecharts
    c = (
        Gauge()
        .add(
            "", 
            [("CPU", 0)], 
            split_number=5, 
            radius="80%",
            start_angle=210,
            end_angle=-30,
            axisline_opts=opts.AxisLineOpts(
                linestyle_opts=opts.LineStyleOpts(
                    color=[(0.3, "#22c55e"), (0.7, "#3b82f6"), (1, "#ef4444")], 
                    width=8
                )
            ),
            pointer=opts.GaugePointerOpts(width=5),
            detail_label_opts=opts.GaugeDetailOpts(
                formatter="{value}%", 
                font_size=20, 
                color="#f8fafc",
                offset_center=[0, "60%"]
            )
        )
        .set_global_opts(
            title_opts=opts.TitleOpts(title=""),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )
    # Get just the options JSON, we'll execute it in our own JS
    chart_options = c.dump_options_with_quotes()

    # Create Connection History Chart using our extension
    history_chart = (
        LineChart(height="300px")
        .add_xaxis([])
        .add_yaxis("Active Connections", [], smooth=True, area=True)
        .set_title("Real-time Traffic")
        .build()
    )
    history_options = history_chart.dump_options()

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gobstopper Mission Control</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <script src="{CurrentConfig.ONLINE_HOST}echarts.min.js"></script>
    <style>
        :root {{ 
            --bg: #020617; 
            --card: rgba(30, 41, 59, 0.5); 
            --card-border: rgba(255, 255, 255, 0.1);
            --text: #f8fafc; 
            --text-dim: #94a3b8;
            --accent: #3b82f6; 
            --primary: #3b82f6;
            --success: #22c55e;
            --danger: #ef4444;
            --glass: rgba(15, 23, 42, 0.6);
        }}
        body {{ 
            font-family: 'Inter', -apple-system, sans-serif; 
            background: radial-gradient(circle at top right, #1e293b, #020617); 
            color: var(--text); 
            margin: 0; 
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 2.5rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--card-border);
        }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; }}
        .card {{ 
            background: var(--card); 
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--card-border);
            border-radius: 1rem; 
            padding: 1.5rem; 
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        .card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 12px 48px 0 rgba(0, 0, 0, 0.4);
            border-color: rgba(255, 255, 255, 0.2);
        }}
        h1 {{ 
            font-size: 1.875rem; 
            font-weight: 700; 
            letter-spacing: -0.025em;
            background: linear-gradient(to right, #60a5fa, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin: 0;
        }}
        h3 {{ 
            margin-top: 0; 
            font-size: 0.875rem; 
            text-transform: uppercase; 
            letter-spacing: 0.05em; 
            color: var(--text-dim);
            margin-bottom: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .metric-container {{ display: flex; flex-wrap: wrap; gap: 1.5rem; }}
        .metric-group {{ flex: 1; min-width: 80px; }}
        .metric {{ font-size: 1.75rem; font-weight: 700; color: #fff; line-height: 1.2; }}
        .metric-label {{ font-size: 0.75rem; color: var(--text-dim); margin-top: 0.25rem; font-weight: 500; }}
        
        table {{ width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 0.5rem; }}
        th, td {{ text-align: left; padding: 1rem; border-bottom: 1px solid var(--card-border); }}
        th {{ color: var(--text-dim); font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
        td {{ font-size: 0.875rem; }}
        
        .status-badge {{ 
            padding: 0.25rem 0.625rem; 
            border-radius: 9999px; 
            font-size: 0.7rem; 
            font-weight: 600; 
            text-transform: uppercase;
        }}
        .status-running {{ background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.2); }}
        .method-badge {{ padding: 0.2rem 0.5rem; border-radius: 0.25rem; font-size: 0.65rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.03em; margin-right: 0.2rem; display: inline-block; }}
        .method-GET    {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.25); }}
        .method-POST   {{ background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.25); }}
        .method-PUT    {{ background: rgba(251, 146, 60, 0.15); color: #fb923c; border: 1px solid rgba(251, 146, 60, 0.25); }}
        .method-DELETE {{ background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.25); }}
        .method-PATCH  {{ background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.25); }}
        .method-WS     {{ background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.25); }}
        .method-OTHER  {{ background: rgba(148, 163, 184, 0.15); color: #94a3b8; border: 1px solid rgba(148, 163, 184, 0.25); }}
        
        .refresh-btn {{ 
            background: rgba(59, 130, 246, 0.1); 
            color: var(--accent); 
            border: 1px solid rgba(59, 130, 246, 0.2);
            padding: 0.5rem 1rem; 
            border-radius: 0.5rem; 
            cursor: pointer; 
            font-weight: 600;
            font-size: 0.875rem;
            transition: all 0.2s;
        }}
        .refresh-btn:hover {{ background: var(--accent); color: white; }}
        
        code {{ font-family: 'JetBrains Mono', monospace; background: rgba(255,255,255,0.05); padding: 0.2rem 0.4rem; border-radius: 0.25rem; }}
        
        #cpu-chart, #history-chart {{ width: 100%; height: 280px; }}
        
        .pulse {{
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 0 rgba(34, 197, 94, 0.4);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }}
            70% {{ transform: scale(1); box-shadow: 0 0 0 6px rgba(34, 197, 94, 0%); }}
            100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0%); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>🍬 Mission Control</h1>
                <p style="color: var(--text-dim); font-size: 0.875rem; margin-top: 0.5rem;">Live system diagnostics for your Gobstopper app</p>
            </div>
            <div style="display: flex; gap: 1rem; align-items: center;">
                <span style="color: #64748b; font-size: 0.875rem; display: flex; align-items: center; gap: 0.5rem;">
                    <span class="pulse"></span> Active
                </span>
                <button class="refresh-btn" onclick="refreshData()">Force Sync</button>
            </div>
        </div>
        
        <div class="grid">
            <div class="card" style="grid-column: 1 / -1;">
                <h3>📟 System Health</h3>
                <div class="metric-container">
                    <div class="metric-group">
                        <div class="metric" id="uptime">-</div>
                        <div class="metric-label">Uptime</div>
                    </div>
                    <div class="metric-group">
                        <div class="metric" id="memory">-</div>
                        <div class="metric-label">Memory RSS</div>
                    </div>
                     <div class="metric-group">
                        <div class="metric" id="routes-count">-</div>
                        <div class="metric-label">Mapped Routes</div>
                    </div>
                </div>
                
                <div id="granian-metrics-row" style="display: none; border-top: 1px solid var(--card-border); margin-top: 1.5rem; padding-top: 1.25rem;">
                    <div class="metric-container">
                        <div class="metric-group">
                            <div class="metric" id="granian-requests">0</div>
                            <div class="metric-label">Total Req</div>
                        </div>
                        <div class="metric-group">
                            <div class="metric" id="granian-active">0</div>
                            <div class="metric-label">Active Conns</div>
                        </div>
                    </div>
                </div>

                <div id="metrics-disabled-hint" style="color: var(--text-dim); font-size: 0.75rem; margin-top: 1.25rem; background: rgba(255,255,255,0.03); padding: 0.75rem; border-radius: 0.5rem;">
                    💡 Metrics disabled. Run with <code style="color: var(--primary);">--dev</code> or <code style="color: var(--primary);">--metrics</code> to see Granian stats.
                </div>
            </div>
            
             <div class="card" style="grid-column: span 2;">
                <h3>📈 Concurrent Connections</h3>
                <div id="history-chart"></div>
            </div>

            <div class="card">
                <h3>⚡ Real-time Load</h3>
                <div id="cpu-chart"></div>
            </div>
        </div>

        <div class="card" style="margin-top: 1.5rem; overflow-x: auto;">
            <h3>🛠️ Background Task Workers</h3>
            <table id="tasks-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Status</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>

        <div class="card" style="margin-top: 1.5rem; overflow-x: auto;">
            <h3>🗺️ Registered Routes</h3>
            <table id="routes-table">
                <thead>
                    <tr>
                        <th>Method(s)</th>
                        <th>Path</th>
                        <th>Handler</th>
                        <th>Blueprint</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        </div>
    </div>

    <script>
        // Init Chart with Pyecharts options
        var chart = echarts.init(document.getElementById('cpu-chart'));
        var options = {chart_options};
        chart.setOption(options);

        var historyChart = echarts.init(document.getElementById('history-chart'));
        var historyOptions = {history_options};
        historyChart.setOption(historyOptions);

        const MAX_POINTS = 30;
        const historyData = [];
        const timeLabels = [];

        // Auth token
        const TOKEN_PARAM = "{token_param}";

        async function refreshData() {{
            try {{
                let url = '/_gobstopper/stats';
                if (TOKEN_PARAM) {{
                    url += '?' + TOKEN_PARAM;
                }}
                
                const res = await fetch(url);
                if (res.status === 403) {{
                    alert("Session expired or unauthorized");
                    return;
                }}
                
                let data;
                try {{
                    data = await res.json();
                }} catch (je) {{
                    const text = await res.text();
                    console.error("Failed to parse JSON. Response was:", text);
                    throw je;
                }}
                
                document.getElementById('uptime').textContent = data.uptime;
                document.getElementById('memory').innerText = data.memory_mb + ' MB';
                document.getElementById('routes-count').innerText = data.routes_count;
                
                // Update Granian metrics if present
                const metricsRow = document.getElementById('granian-metrics-row');
                const metricsHint = document.getElementById('metrics-disabled-hint');

                if (data.metrics_enabled) {{
                    if (metricsRow) metricsRow.style.display = 'contents';
                    if (metricsHint) metricsHint.style.display = 'none';
                    
                    if (data.granian) {{
                        if (document.getElementById('granian-requests')) 
                            document.getElementById('granian-requests').innerText = data.granian.requests.toLocaleString();
                        if (document.getElementById('granian-active'))
                            document.getElementById('granian-active').innerText = data.granian.active_connections;
                    }}
                }} else {{
                    if (metricsRow) metricsRow.style.display = 'none';
                    if (metricsHint) metricsHint.style.display = 'block';
                }}

                // Update tasks
                // Update Charts
                chart.setOption({{
                    series: [{{
                        data: [{{value: data.cpu_percent, name: 'CPU'}}]
                    }}]
                }});

                if (data.metrics_enabled && data.granian) {{
                    const now = new Date().toLocaleTimeString();
                    const val = data.granian.active_connections;
                    
                    historyData.push(val);
                    timeLabels.push(now);
                    
                    if (historyData.length > MAX_POINTS) {{
                        historyData.shift();
                        timeLabels.shift();
                    }}
                    
                    historyChart.setOption({{
                        xAxis: {{ data: timeLabels }},
                        series: [{{ data: historyData }}]
                    }});
                }}
                
                const tbody = document.querySelector('#tasks-table tbody');
                tbody.innerHTML = '';
                
                // Mock tasks for now if empty
                const tasks = data.tasks || [];
                if (tasks.length === 0) {{
                     tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color: #94a3b8;">No active tasks</td></tr>';
                }} else {{
                    tasks.forEach(task => {{
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td>${{task.id.substring(0,8)}}</td>
                            <td>${{task.name}}</td>
                            <td><span class="status-badge status-running">${{task.status}}</span></td>
                            <td>${{new Date(task.created_at * 1000).toLocaleTimeString()}}</td>
                        `;
                        tbody.appendChild(tr);
                    }});
                }}
            }} catch (e) {{
                console.error("Failed to fetch stats", e);
            }}
        }}
        
        async function loadRoutes() {{
            try {{
                let url = '/_gobstopper/routes';
                if (TOKEN_PARAM) url += '?' + TOKEN_PARAM;
                const res = await fetch(url);
                if (!res.ok) return;
                const routes = await res.json();
                const tbody = document.querySelector('#routes-table tbody');
                tbody.innerHTML = '';
                if (routes.length === 0) {{
                    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#94a3b8;">No routes registered</td></tr>';
                    return;
                }}
                const KNOWN_METHODS = ['GET','POST','PUT','DELETE','PATCH','WS'];
                routes.forEach(r => {{
                    const badges = r.methods.map(m => {{
                        const cls = KNOWN_METHODS.includes(m) ? 'method-' + m : 'method-OTHER';
                        return `<span class="method-badge ${{cls}}">${{m}}</span>`;
                    }}).join('');
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${{badges}}</td>
                        <td><code>${{r.pattern}}</code></td>
                        <td>${{r.name}}</td>
                        <td style="color:var(--text-dim)">${{r.blueprint || '—'}}</td>
                    `;
                    tbody.appendChild(tr);
                }});
            }} catch (e) {{
                console.error('Failed to load routes', e);
            }}
        }}

        // Auto refresh
        refreshData();
        setInterval(refreshData, 2000);
        document.addEventListener('DOMContentLoaded', loadRoutes);
        // Also call immediately in case DOM is already loaded
        loadRoutes();

        window.addEventListener('resize', function() {{
            chart.resize();
            historyChart.resize();
        }});
    </script>
</body>
</html>
"""

START_TIME = time.time()
_PROCESS_CACHE = None

def get_process():
    global _PROCESS_CACHE
    if _PROCESS_CACHE is None:
        _PROCESS_CACHE = psutil.Process(os.getpid())
        # Initial call to seed it
        _PROCESS_CACHE.cpu_percent()
    return _PROCESS_CACHE

async def _scrape_granian_metrics(port: int) -> dict:
    """Scrape and parse Granian Prometheus metrics."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{port}/metrics", timeout=0.5) as resp:
                if resp.status != 200:
                    return {}
                text = await resp.text()
                
                metrics = {}
                for line in text.splitlines():
                    if line.startswith("#") or not line.strip():
                        continue
                    try:
                        name, value = line.split(None, 1)
                        # Granian metrics often have labels like {worker="0"}, just strip them for simplicity here
                        clean_name = name.split('{')[0]
                        metrics[clean_name] = float(value)
                    except (ValueError, IndexError):
                        continue
                return metrics
    except Exception:
        return {}

@dashboard.get("/")
async def index(request: Request):
    if not check_auth(request):
        return Response("<h1>403 Forbidden</h1><p>Missing or invalid access token.</p>", status=403, content_type="text/html")
        
    token_param = ""
    if DASHBOARD_TOKEN:
        token_param = f"token={DASHBOARD_TOKEN}"
        
    return Response(get_base_html(token_param), content_type="text/html")

@dashboard.get("/routes")
async def routes_list(request: Request):
    if not check_auth(request):
        return Response({"error": "Unauthorized"}, status=403, content_type="application/json")

    app = request.app
    result = []
    for r in getattr(app, "_all_routes", []):
        if r.is_websocket:
            methods = ["WS"]
        else:
            methods = list(r.methods) if r.methods else ["GET"]
        blueprint_name = None
        chain = getattr(r, "blueprint_chain", None)
        if chain:
            blueprint_name = getattr(chain[-1], "name", None)
        result.append({
            "pattern": r.pattern,
            "methods": methods,
            "name": getattr(r.handler, "__name__", str(r.handler)),
            "is_websocket": r.is_websocket,
            "blueprint": blueprint_name,
            "params": getattr(r, "path_params", []) or [],
        })
    return JSONResponse(result)


@dashboard.get("/stats")
async def stats(request: Request):
    if not check_auth(request):
        return Response({"error": "Unauthorized"}, status=403, content_type="application/json")

    process = get_process()
    mem_info = process.memory_info()
    
    app = request.app
    task_queue = getattr(app, 'task_queue', None)
    
    # Get active tasks (simple list from queue if possible)
    tasks = []
    if task_queue:
        for task_id, task in task_queue.running_tasks.items():
            tasks.append({
                "id": task.id,
                "name": task.name,
                "status": task.status.value,
                "created_at": task.created_at.timestamp()
            })
    
    # Route count
    routes_count = len(getattr(app, '_all_routes', []))

    # Scrape Granian metrics if enabled
    granian_stats = {}
    if getattr(app, 'metrics_enabled', False):
        granian_stats = await _scrape_granian_metrics(getattr(app, 'metrics_port', 9090))

    return JSONResponse({
        "uptime": str(datetime.timedelta(seconds=int(time.time() - START_TIME))),
        "memory_mb": round(mem_info.rss / 1024 / 1024, 1),
        "cpu_percent": process.cpu_percent(),
        "routes_count": routes_count,
        "metrics_enabled": getattr(app, 'metrics_enabled', False),
        "tasks": tasks,
        "granian": {
            "requests": granian_stats.get("granian_requests_handled", 0),
            "active_connections": granian_stats.get("granian_connections_active", 0),
            "py_wait": round(granian_stats.get("granian_py_wait_cumulative", 0), 3),
            "respawns": granian_stats.get("granian_workers_respawns_total", 0)
        }
    })
