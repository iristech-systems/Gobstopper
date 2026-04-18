#!/usr/bin/env python3
"""Gobstopper EDA example with HTML UI + Datastar + OpenAPI.

What this demonstrates:
- EDA dispatcher/store bootstrap via `init_eda_from_env(...)`
- Event fanout across topics (`orders.created` -> billing + notifications)
- Dead-letter inspection and replay endpoints
- `gobstopper.html` dashboard UI
- Datastar live updates via SSE stream
- OpenAPI docs for core operational endpoints

Run:
    python example_eda_app.py

Try:
    open http://127.0.0.1:8000/
    open http://127.0.0.1:8000/openapi

Deployment note:
    For multi-worker production, use a remote Surreal endpoint for shared writable
    state. Embedded/local stores are best for single-worker/dev usage.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any

from gobstopper import Gobstopper, Request, jsonify
from gobstopper.extensions.datastar import Datastar, datastar_response, datastar_script, MergeMode
from gobstopper.extensions.charts import ChartExtension, chart_runtime_script
from gobstopper.extensions.openapi import attach_openapi
from gobstopper.extensions.openapi.decorators import doc, response, request_body, param
from gobstopper.html import (
    html,
    head,
    body,
    main,
    section,
    article,
    div,
    h1,
    h2,
    h3,
    p,
    ul,
    li,
    button,
    style,
    meta,
    script,
    code,
    raw_html,
)
from gobstopper.html.datastar import init as ds_init, on_click


app = Gobstopper(__name__, debug=True)

try:
    charts = ChartExtension(app, default_height="260px")
except Exception:
    charts = None

attach_openapi(
    app,
    title="Gobstopper EDA Example",
    version="0.5.0",
    description="EDA demo with Datastar live dashboard and operational endpoints",
)

TOPICS = ["orders.created", "billing.charge", "notifications.email"]

dispatcher = app.init_eda_from_env(
    topics=TOPICS,
    consumer_group=os.getenv("EDA_CONSUMER_GROUP", "example-eda-ui"),
    autostart=True,
)

DEMO_STATE: dict[str, Any] = {
    "orders_received": 0,
    "billing_success": 0,
    "billing_failed": 0,
    "emails_sent": 0,
    "recent": [],
}


def _record(action: str, data: dict[str, Any]) -> None:
    DEMO_STATE["recent"].append(
        {"ts": time.time(), "action": action, "data": data}
    )
    DEMO_STATE["recent"] = DEMO_STATE["recent"][-25:]


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _stats_fragment() -> Any:
    return article(id="eda-stats", class_="panel")[
        h3["Pipeline Metrics"],
        div(class_="stats-grid")[
            div(class_="stat")[p(class_="label")["Orders"], p(class_="value")[str(DEMO_STATE["orders_received"]) ]],
            div(class_="stat")[p(class_="label")["Billing OK"], p(class_="value ok")[str(DEMO_STATE["billing_success"]) ]],
            div(class_="stat")[p(class_="label")["Billing Failed"], p(class_="value bad")[str(DEMO_STATE["billing_failed"]) ]],
            div(class_="stat")[p(class_="label")["Emails Sent"], p(class_="value")[str(DEMO_STATE["emails_sent"]) ]],
        ],
    ]


def _build_pipeline_chart() -> Any | None:
    if charts is None:
        return None
    return (
        charts.bar(width="100%", height="260px", id="eda_pipeline_chart")
        .add_xaxis(["Orders", "Billing OK", "Billing Failed", "Emails"])
        .add_yaxis(
            "Count",
            [
                DEMO_STATE["orders_received"],
                DEMO_STATE["billing_success"],
                DEMO_STATE["billing_failed"],
                DEMO_STATE["emails_sent"],
            ],
        )
        .set_title("EDA Pipeline Throughput")
        .set_tooltip(trigger="item")
        .build()
    )


def _chart_fragment() -> Any:
    if charts is None:
        return article(id="eda-chart", class_="panel")[
            h3["Pipeline Chart"],
            p(class_="muted")[
                "Charts extension unavailable. Install optional chart dependencies to enable."
            ],
        ]

    chart = _build_pipeline_chart()

    return article(id="eda-chart", class_="panel")[
        h3["Pipeline Chart"],
        p(class_="muted")[
            "Rendered via charts extension and managed with a tiny client helper."
        ],
        raw_html(chart.container if chart is not None else "<div id='eda_pipeline_chart'></div>"),
    ]


def _recent_fragment() -> Any:
    items = list(reversed(DEMO_STATE["recent"][-10:]))
    recent_node = (
        ul(class_="recent")[[
            li[
                code[_fmt_ts(entry["ts"])],
                " ",
                code[entry["action"]],
                " ",
                str(entry["data"]),
            ]
            for entry in items
        ]]
        if items
        else p(class_="muted")["No events yet."]
    )
    return article(id="eda-recent", class_="panel")[
        h3["Recent Activity"],
        recent_node,
    ]


async def _dlq_fragment(topic: str = "billing.charge") -> Any:
    rows = []
    if app.eda_store is not None:
        rows = await app.eda_store.list_dead_letters(
            topic,
            app._eda_consumer_group,
            limit=6,
            offset=0,
        )

    dlq_node = (
        ul(class_="recent")[[
            li[
                code[row.id],
                " attempts=",
                str(row.delivery_attempt),
                "/",
                str(row.max_deliveries),
                " error=",
                str(row.last_error or "-"),
            ]
            for row in rows
        ]]
        if rows
        else p(class_="muted")["No dead-letter events."]
    )

    return article(id="eda-dlq", class_="panel")[
        h3[f"DLQ ({topic})"],
        p(class_="muted")[f"Count: {len(rows)}"],
        dlq_node,
    ]


async def _status_fragment(text: str, tone: str = "info") -> Any:
    return div(id="eda-status", class_=f"status {tone}")[text]


async def _dashboard_page() -> Any:
    return html(lang="en")[
        head[
            meta(charset="utf-8"),
            meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            style[
                """
                :root { --bg:#f8fbff; --card:#fff; --line:#d9e3ef; --ink:#17233a; --muted:#627084; --ok:#0e7a56; --bad:#c2410c; }
                * { box-sizing: border-box; }
                body { margin:0; font-family: 'Avenir Next','Segoe UI',sans-serif; color:var(--ink); background: radial-gradient(circle at 80% 0%, rgba(66,153,225,.12), transparent 40%), var(--bg); }
                main { max-width: 1100px; margin: 0 auto; padding: 28px 18px 42px; }
                .hero { margin-bottom: 14px; }
                .hero h1 { margin: 0 0 8px; }
                .hero p { margin: 0; color: var(--muted); }
                .row { display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 14px; margin-top: 14px; }
                .panel { background:var(--card); border:1px solid var(--line); border-radius: 14px; padding: 14px; box-shadow: 0 10px 28px rgba(23,35,58,.06); }
                .panel h3 { margin: 0 0 8px; font-size: 1rem; }
                .stats-grid { display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px; }
                .stat { border:1px solid var(--line); border-radius:10px; padding:10px; background:#fbfdff; }
                .label { margin:0 0 4px; color:var(--muted); font-size:.8rem; text-transform: uppercase; letter-spacing: .05em; }
                .value { margin:0; font-size:1.25rem; font-weight:700; }
                .value.ok { color: var(--ok); }
                .value.bad { color: var(--bad); }
                .controls { display:flex; gap:10px; flex-wrap: wrap; margin-top: 14px; }
                button { border:1px solid var(--line); background:#fff; border-radius:10px; padding:10px 14px; cursor:pointer; font-weight: 600; }
                button:hover { border-color:#9db6d3; }
                button.bad { color:#fff; background:#be3f0a; border-color:#be3f0a; }
                button.ok { color:#fff; background:#0e7a56; border-color:#0e7a56; }
                .status { margin-top: 12px; padding:10px 12px; border-radius:10px; border:1px solid var(--line); background:#f5f9ff; }
                .status.ok { border-color:#b7e3d4; background:#effaf5; }
                .status.warn { border-color:#f2c8ad; background:#fff3eb; }
                .muted { color: var(--muted); }
                .recent { margin:0; padding-left: 18px; display:grid; gap:6px; }
                @media (max-width: 900px) { .row { grid-template-columns: 1fr; } }
                """
            ],
            datastar_script(),
            chart_runtime_script(charts.get_cdn_url()) if charts is not None else "",
            raw_html("""
                <script>
                document.addEventListener('DOMContentLoaded', function () {
                  if (window.GobstopperCharts) {
                    window.GobstopperCharts.fetchAndSet('eda_pipeline_chart', '/eda/chart-option', 'option');
                  }
                });
                </script>
            """),
        ],
        body[
            main(**ds_init("/eda/stream"))[
                section(class_="hero")[
                    h1["Gobstopper EDA Dashboard"],
                    p[
                        "Live event pipeline using Surreal-backed store + dispatcher. "
                        "This page is rendered with gobstopper.html and updated with Datastar SSE."
                    ],
                    p(class_="muted")[
                        "OpenAPI: ",
                        code["/openapi"],
                        " | JSON spec: ",
                        code["/openapi.json"],
                    ],
                ],
                div(class_="controls")[
                    button(class_="ok", **on_click("@post('/eda/actions/create-good-order')"))["Create healthy order"],
                    button(class_="bad", **on_click("@post('/eda/actions/create-failing-order')"))["Create failing order"],
                    button(**on_click("@post('/eda/actions/replay-billing')"))["Replay billing DLQ"],
                    button(type="button", onclick="window.GobstopperCharts.fetchAndSet('eda_pipeline_chart','/eda/chart-option','option');")[
                        "Refresh chart"
                    ],
                ],
                await _status_fragment("Ready."),
                div(class_="row")[
                    _stats_fragment(),
                    await _dlq_fragment("billing.charge"),
                    _recent_fragment(),
                ],
                div(class_="row")[
                    _chart_fragment(),
                ],
            ]
        ],
    ]


async def handle_order_created(event):
    payload = event.payload or {}
    DEMO_STATE["orders_received"] += 1
    _record("orders.created", {"event_id": event.id, "payload": payload})

    await dispatcher.publish(
        "billing.charge",
        {
            "order_id": payload.get("order_id"),
            "amount": payload.get("amount", 0),
            "force_fail": payload.get("force_billing_failure", False),
        },
        key=str(payload.get("order_id", "")),
        idempotency_key=f"billing:{payload.get('order_id', event.id)}",
        producer="example-eda-app",
    )

    await dispatcher.publish(
        "notifications.email",
        {
            "order_id": payload.get("order_id"),
            "email": payload.get("customer_email", "unknown@example.com"),
        },
        key=str(payload.get("order_id", "")),
        producer="example-eda-app",
    )


async def handle_billing_charge(event):
    payload = event.payload or {}
    await asyncio.sleep(0.05)

    if payload.get("force_fail"):
        DEMO_STATE["billing_failed"] += 1
        _record("billing.charge.failed", {"event_id": event.id, "payload": payload})
        raise RuntimeError("simulated billing processor failure")

    DEMO_STATE["billing_success"] += 1
    _record("billing.charge.success", {"event_id": event.id, "payload": payload})


async def handle_notifications_email(event):
    payload = event.payload or {}
    await asyncio.sleep(0.01)
    email = str(payload.get("email", ""))

    if email.endswith("@fail.local"):
        _record("notifications.email.failed", {"event_id": event.id, "payload": payload})
        raise RuntimeError("simulated email provider failure")

    DEMO_STATE["emails_sent"] += 1
    _record("notifications.email.sent", {"event_id": event.id, "payload": payload})


dispatcher.register_handler("orders.created", handle_order_created)
dispatcher.register_handler("billing.charge", handle_billing_charge)
dispatcher.register_handler("notifications.email", handle_notifications_email)


@app.get("/")
async def index(request: Request):
    del request
    return await _dashboard_page()


@app.get("/eda/stream")
async def eda_stream(request: Request):
    del request

    async def generator():
        while True:
            dlq = await _dlq_fragment("billing.charge")
            events = Datastar.merge_many([_stats_fragment(), _recent_fragment(), dlq])
            yield events
            await asyncio.sleep(1.0)

    return Datastar.stream(generator())


@app.post("/eda/actions/create-good-order")
async def action_create_good_order(request: Request):
    del request
    order_id = f"ord-good-{int(time.time() * 1000)}"
    await dispatcher.publish(
        "orders.created",
        {
            "order_id": order_id,
            "amount": 49.95,
            "customer_email": "good@example.com",
            "force_billing_failure": False,
        },
        key=order_id,
        idempotency_key=f"order:{order_id}",
        producer="example-eda-app",
    )
    return datastar_response(
        merge=[
            (
                await _status_fragment(f"Queued healthy order {order_id}", "ok"),
                "#eda-status",
                MergeMode.REPLACE_ELEMENT,
                None,
            )
        ]
    )


@app.post("/eda/actions/create-failing-order")
async def action_create_failing_order(request: Request):
    del request
    order_id = f"ord-bad-{int(time.time() * 1000)}"
    await dispatcher.publish(
        "orders.created",
        {
            "order_id": order_id,
            "amount": 99.0,
            "customer_email": "ops@fail.local",
            "force_billing_failure": True,
        },
        key=order_id,
        idempotency_key=f"order:{order_id}",
        producer="example-eda-app",
    )
    return datastar_response(
        merge=[
            (
                await _status_fragment(
                    f"Queued failing order {order_id} (expected DLQ)", "warn"
                ),
                "#eda-status",
                MergeMode.REPLACE_ELEMENT,
                None,
            )
        ]
    )


@app.post("/eda/actions/replay-billing")
async def action_replay_billing(request: Request):
    del request
    topic = "billing.charge"
    replayed = 0
    rows = []
    if app.eda_store is not None and hasattr(app.eda_store, "requeue_dead_letter"):
        rows = await app.eda_store.list_dead_letters(
            topic,
            app._eda_consumer_group,
            limit=20,
            offset=0,
        )
        for row in rows:
            ok = await app.eda_store.requeue_dead_letter(
                row.id,
                app._eda_consumer_group,
                expected_topic=topic,
            )
            if ok:
                replayed += 1

    return datastar_response(
        merge=[
            (
                await _status_fragment(
                    f"Replay requested={len(rows)} replayed={replayed} for {topic}",
                    "ok" if replayed else "warn",
                ),
                "#eda-status",
                MergeMode.REPLACE_ELEMENT,
                None,
            )
        ]
    )


@app.get("/eda/chart-option")
@doc(summary="Get EDA chart option", tags=["EDA"])
@response(200, description="Current EDA chart option")
async def eda_chart_option(request: Request):
    del request
    chart = _build_pipeline_chart()
    option = json.loads(chart.dump_options()) if chart is not None else {}
    return jsonify({"option": option})


@app.post("/orders")
@doc(summary="Create order event", tags=["EDA"])
@request_body(
    content={
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "amount": {"type": "number"},
                    "customer_email": {"type": "string"},
                    "force_billing_failure": {"type": "boolean"},
                },
                "required": ["amount"],
            }
        }
    }
)
@response(
    202,
    description="Order event accepted",
    content={
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "accepted": {"type": "boolean"},
                    "event_id": {"type": "string"},
                    "topic": {"type": "string"},
                    "order_id": {"type": "string"},
                },
            }
        }
    },
)
async def create_order(request: Request):
    data = await request.get_json() or {}
    order_id = str(data.get("order_id") or f"ord-{int(time.time() * 1000)}")

    event = await dispatcher.publish(
        "orders.created",
        {
            "order_id": order_id,
            "amount": float(data.get("amount", 0.0)),
            "customer_email": data.get("customer_email", "customer@example.com"),
            "force_billing_failure": bool(data.get("force_billing_failure", False)),
        },
        key=order_id,
        idempotency_key=f"order:{order_id}",
        producer="example-eda-app",
    )

    return jsonify(
        {
            "accepted": True,
            "event_id": event.id,
            "topic": event.topic,
            "order_id": order_id,
        },
        status=202,
    )


@app.get("/eda/state")
@doc(summary="Get EDA runtime state", tags=["EDA"])
@response(200, description="Current EDA state")
async def eda_state(request: Request):
    del request
    return jsonify(
        {
            "mode": app.eda_config.mode.value if app.eda_config else None,
            "store": app.eda_config.store if app.eda_config else None,
            "broker": app.eda_config.broker if app.eda_config else None,
            "surreal_url": app.eda_config.surreal_url if app.eda_config else None,
            "stats": {
                "orders_received": DEMO_STATE["orders_received"],
                "billing_success": DEMO_STATE["billing_success"],
                "billing_failed": DEMO_STATE["billing_failed"],
                "emails_sent": DEMO_STATE["emails_sent"],
            },
            "recent": DEMO_STATE["recent"],
        }
    )


@app.get("/eda/dlq/<topic>")
@doc(summary="List dead-letter events by topic", tags=["EDA"])
@param(name="topic", in_="path", required=True, schema=str, description="Topic")
@param(name="limit", in_="query", required=False, schema=int, description="Max rows")
@response(200, description="Dead-letter events")
async def list_dead_letters(request: Request, topic: str):
    if app.eda_store is None:
        return jsonify({"error": "EDA store is not configured"}, status=500)

    raw_limit = request.args.get("limit", ["20"])
    try:
        limit = max(1, int(raw_limit[0]))
    except Exception:
        limit = 20

    rows = await app.eda_store.list_dead_letters(
        topic,
        app._eda_consumer_group,
        limit=limit,
        offset=0,
    )

    return jsonify(
        {
            "topic": topic,
            "count": len(rows),
            "items": [
                {
                    "id": event.id,
                    "delivery_attempt": event.delivery_attempt,
                    "max_deliveries": event.max_deliveries,
                    "last_error": event.last_error,
                    "dead_lettered_at": (
                        event.dead_lettered_at.isoformat()
                        if event.dead_lettered_at
                        else None
                    ),
                }
                for event in rows
            ],
        }
    )


@app.post("/eda/replay")
@doc(summary="Replay dead-letter events", tags=["EDA"])
@request_body(
    content={
        "application/json": {
            "schema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "event_id": {"type": "string"},
                    "all": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
            }
        }
    }
)
@response(200, description="Replay result")
async def replay_dead_letters(request: Request):
    if app.eda_store is None or not hasattr(app.eda_store, "requeue_dead_letter"):
        return jsonify({"error": "EDA store does not support replay"}, status=500)

    body = await request.get_json() or {}
    topic = str(body.get("topic", "billing.charge"))
    event_id = body.get("event_id")
    replay_all = bool(body.get("all", False))
    limit = int(body.get("limit", 50))

    if event_id:
        ok = await app.eda_store.requeue_dead_letter(
            str(event_id),
            app._eda_consumer_group,
            expected_topic=topic,
        )
        return jsonify({"event_id": event_id, "replayed": bool(ok), "topic": topic})

    if not replay_all:
        return jsonify(
            {
                "error": "set event_id or all=true",
                "example": {"topic": topic, "all": True, "limit": 20},
            },
            status=400,
        )

    rows = await app.eda_store.list_dead_letters(
        topic,
        app._eda_consumer_group,
        limit=max(1, limit),
        offset=0,
    )

    replayed = 0
    for row in rows:
        ok = await app.eda_store.requeue_dead_letter(
            row.id,
            app._eda_consumer_group,
            expected_topic=topic,
        )
        if ok:
            replayed += 1

    return jsonify({"topic": topic, "requested": len(rows), "replayed": replayed})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=1, reload=True)
