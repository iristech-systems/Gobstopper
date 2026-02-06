
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
        .add("", [("CPU", 0)], split_number=5, detail_label_opts=opts.LabelOpts(formatter="{value}%"))
        .set_global_opts(
            title_opts=opts.TitleOpts(title=""),
            legend_opts=opts.LegendOpts(is_show=False),
        )
    )
    # Get just the options JSON, we'll execute it in our own JS
    chart_options = c.dump_options_with_quotes()

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gobstopper Mission Control</title>
    <script src="{CurrentConfig.ONLINE_HOST}echarts.min.js"></script>
    <style>
        :root {{ --bg: #0f172a; --card: #1e293b; --text: #f8fafc; --accent: #3b82f6; --success: #22c55e; }}
        body {{ font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; }}
        .card {{ background: var(--card); border-radius: 0.5rem; padding: 1.5rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
        h1, h2, h3 {{ margin-top: 0; }}
        .metric {{ font-size: 2rem; font-weight: bold; color: var(--accent); }}
        .metric-label {{ font-size: 0.875rem; color: #94a3b8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ text-align: left; padding: 0.75rem; border-bottom: 1px solid #334155; }}
        th {{ color: #94a3b8; font-weight: 500; }}
        .status-badge {{ padding: 0.25rem 0.5rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }}
        .status-running {{ background: rgba(34, 197, 94, 0.2); color: var(--success); }}
        .refresh-btn {{ background: var(--accent); color: white; border: none; padding: 0.5rem 1rem; border-radius: 0.25rem; cursor: pointer; }}
        #cpu-chart {{ width: 100%; height: 300px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🍬 Mission Control</h1>
            <div style="display: flex; gap: 1rem; align-items: center;">
                <span style="color: #64748b; font-size: 0.875rem;">Status: Live</span>
                <button class="refresh-btn" onclick="refreshData()">Refresh</button>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>System Status</h3>
                <div style="display: flex; gap: 2rem;">
                    <div>
                        <div class="metric" id="uptime">-</div>
                        <div class="metric-label">Uptime</div>
                    </div>
                    <div>
                        <div class="metric" id="memory">-</div>
                        <div class="metric-label">Memory</div>
                    </div>
                     <div>
                        <div class="metric" id="routes-count">-</div>
                        <div class="metric-label">Routes</div>
                    </div>
                </div>
            </div>
            
             <div class="card">
                <h3>Real-time Load</h3>
                <div id="cpu-chart"></div>
            </div>
        </div>

        <div class="card" style="margin-top: 1.5rem;">
            <h3>Background Tasks</h3>
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
    </div>

    <script>
        // Init Chart with Pyecharts options
        var chart = echarts.init(document.getElementById('cpu-chart'));
        var options = {chart_options};
        chart.setOption(options);

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
                
                const data = await res.json();
                
                document.getElementById('uptime').textContent = data.uptime;
                document.getElementById('memory').textContent = data.memory_mb + ' MB';
                document.getElementById('routes-count').textContent = data.routes_count;
                
                // Update Chart
                chart.setOption({{
                    series: [{{
                        data: [{{value: data.cpu_percent, name: 'CPU'}}]
                    }}]
                }});
                
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
        
        // Auto refresh
        refreshData();
        setInterval(refreshData, 2000);
        
        window.addEventListener('resize', function() {{
            chart.resize();
        }});
    </script>
</body>
</html>
"""

START_TIME = time.time()

@dashboard.get("/")
async def index(request: Request):
    if not check_auth(request):
        return Response("<h1>403 Forbidden</h1><p>Missing or invalid access token.</p>", status=403, content_type="text/html")
        
    token_param = ""
    if DASHBOARD_TOKEN:
        token_param = f"token={DASHBOARD_TOKEN}"
        
    return Response(get_base_html(token_param), content_type="text/html")

@dashboard.get("/stats")
async def stats(request: Request):
    if not check_auth(request):
        return Response({"error": "Unauthorized"}, status=403, content_type="application/json")

    process = psutil.Process(os.getpid())
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

    return JSONResponse({
        "uptime": str(datetime.timedelta(seconds=int(time.time() - START_TIME))),
        "memory_mb": round(mem_info.rss / 1024 / 1024, 1),
        "cpu_percent": process.cpu_percent(),
        "routes_count": routes_count,
        "tasks": tasks
    })
