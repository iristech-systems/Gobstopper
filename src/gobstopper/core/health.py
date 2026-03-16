"""
Built-in health / readiness endpoints for container orchestration.

Routes
------
GET /health  — liveness probe: always 200 if the process is alive.
GET /ready   — readiness probe: 200 when all subsystems are operational,
               503 when any subsystem reports a problem.

Both endpoints are intentionally public (no auth) following the standard
Kubernetes / Docker-health-probe pattern.
"""

from importlib.metadata import version, PackageNotFoundError

from ..core.blueprint import Blueprint
from ..http.request import Request
from ..http.response import JSONResponse

health_bp = Blueprint("health")


def _app_version() -> str:
    try:
        return version("gobstopper")
    except PackageNotFoundError:
        return "dev"


@health_bp.get("/health")
async def liveness(request: Request):
    """Liveness probe — always 200 if the process is alive."""
    return JSONResponse({"status": "ok", "version": _app_version()})


@health_bp.get("/ready")
async def readiness(request: Request):
    """Readiness probe — checks optional subsystems."""
    app = request.app
    checks: dict[str, str] = {}
    degraded = False

    # Task queue check
    task_queue = getattr(app, "task_queue", None)
    if task_queue is not None:
        try:
            # A truthy task_queue with an initialised db is considered ready.
            # Avoid blocking I/O — just inspect the object state.
            if getattr(task_queue, "_db", None) is None and not getattr(task_queue, "_initialized", True):
                raise RuntimeError("queue not initialised")
            checks["tasks"] = "ok"
        except Exception as exc:
            checks["tasks"] = f"error: {exc}"
            degraded = True

    status = "degraded" if degraded else "ok"
    http_status = 503 if degraded else 200
    return JSONResponse({"status": status, "checks": checks}, status=http_status)
