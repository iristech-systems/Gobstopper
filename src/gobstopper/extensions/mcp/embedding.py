"""
Knowledge MCP Extension for Gobstopper.

Opinionated 4-step document embedding pipeline exposed as MCP tools.

Pipeline: INGEST → EXTRACT_NORMALIZE → CHUNK_EMBED → CONNECT_INDEX

Every step runs in order. No step may run before the previous succeeds.
"""

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from ..mcp import MCP


class PipelineStep(str, Enum):
    """The 4 canonical pipeline steps in execution order."""

    INGEST = "ingest"
    EXTRACT_NORMALIZE = "extract_normalize"
    CHUNK_EMBED = "chunk_embed"
    CONNECT_INDEX = "connect_index"

    @classmethod
    def ordered(cls) -> List["PipelineStep"]:
        return [cls.INGEST, cls.EXTRACT_NORMALIZE, cls.CHUNK_EMBED, cls.CONNECT_INDEX]

    def previous(self) -> Optional["PipelineStep"]:
        order = self.ordered()
        idx = order.index(self)
        return order[idx - 1] if idx > 0 else None

    def next(self) -> Optional["PipelineStep"]:
        order = self.ordered()
        idx = order.index(self)
        return order[idx + 1] if idx < len(order) - 1 else None


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StepResult:
    """Result from a single step execution."""

    output: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class StepState:
    """State of a single pipeline step."""

    status: StepStatus = StepStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    result: Optional[StepResult] = None


@dataclass
class PipelineRun:
    """A complete pipeline run with step states."""

    run_id: str
    tenant_id: str
    partner_id: str
    source_kind: str
    source_value: str
    idempotency_key: str
    source_hash: Optional[str] = None
    status: RunStatus = RunStatus.PENDING
    current_step: Optional[PipelineStep] = None
    steps: Dict[PipelineStep, StepState] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None

    def to_output(self) -> Dict[str, Any]:
        """Convert to MCP output schema."""
        return {
            "pipeline_run_id": self.run_id,
            "status": self.status.value,
            "current_step": self.current_step.value if self.current_step else None,
            "step_status": {
                step.value: state.status.value for step, state in self.steps.items()
            },
            "metrics": self.metrics,
            "errors": self.errors,
        }


@dataclass
class PipelineContext:
    """Context passed to each step handler."""

    run: PipelineRun
    step: PipelineStep
    tenant_id: str
    partner_id: str
    source: Dict[str, str]
    options: Dict[str, Any]
    requested_by: Dict[str, str]

    def __getattr__(self, name: str) -> Any:
        """Allow dict-style access to source."""
        if name in ("kind", "value"):
            return self.source.get(name)
        raise AttributeError(name)


class StepHandler:
    """A handler for a pipeline step."""

    def __init__(
        self,
        step: PipelineStep,
        handler: Callable,
        validator: Optional[Callable] = None,
        timeout: int = 300,
        retries: int = 2,
    ):
        self.step = step
        self.handler = handler
        self.validator = validator
        self.timeout = timeout
        self.retries = retries


class PipelinePolicy:
    """Base class for pipeline policies."""

    async def before_run(self, ctx: PipelineContext) -> None:
        """Called before pipeline starts. Raise to reject."""
        pass

    async def after_step(
        self, ctx: PipelineContext, step: PipelineStep, result: StepResult
    ) -> None:
        """Called after each step succeeds."""
        pass

    async def on_failure(
        self, ctx: PipelineContext, step: PipelineStep, error: str
    ) -> None:
        """Called when a step fails after retries."""
        pass


class FingerprintDedupePolicy(PipelinePolicy):
    """Compute content hash and short-circuit if already indexed."""

    def __init__(self, chunks_collection):
        self.chunks = chunks_collection

    async def before_run(self, ctx: PipelineContext) -> None:
        if ctx.source.get("kind") == "blob_ref":
            content = await self._get_content(ctx.source["value"])
            fingerprint = hashlib.sha256(content).hexdigest()

            existing = await self.chunks.find_one(
                tenant_id=ctx.tenant_id,
                partner_id=ctx.partner_id,
                fingerprint=fingerprint,
                embedding_model=ctx.options.get("embedding_model"),
            )
            if existing:
                ctx.run.status = RunStatus.SUCCEEDED
                ctx.run.metrics["reused"] = True
                ctx.run.metrics["existing_chunk_id"] = existing.id


class TenantIsolationPolicy(PipelinePolicy):
    """Hard reject if source tenant doesn't match request tenant."""

    async def before_run(self, ctx: PipelineContext) -> None:
        source_tenant = ctx.source.get("tenant_id")
        if source_tenant and source_tenant != ctx.tenant_id:
            raise PermissionError(
                f"Tenant mismatch: source={source_tenant}, request={ctx.tenant_id}"
            )


class QualityGatePolicy(PipelinePolicy):
    """Validate step outputs meet quality thresholds."""

    def __init__(
        self,
        min_text_chars: int = 100,
        max_empty_chunk_ratio: float = 0.1,
    ):
        self.min_text_chars = min_text_chars
        self.max_empty_chunk_ratio = max_empty_chunk_ratio

    async def after_step(
        self, ctx: PipelineContext, step: PipelineStep, result: StepResult
    ) -> None:
        if step == PipelineStep.EXTRACT_NORMALIZE:
            text = (
                result.output.get("text", "")
                if isinstance(result.output, dict)
                else str(result.output)
            )
            if len(text.strip()) < self.min_text_chars:
                raise ValueError(
                    f"Extracted text below minimum threshold: {len(text)} chars"
                )

        if step == PipelineStep.CHUNK_EMBED:
            chunks = (
                result.output.get("chunks", [])
                if isinstance(result.output, dict)
                else []
            )
            if not chunks:
                raise ValueError("No chunks produced")

            empty = sum(1 for c in chunks if not c.get("text", "").strip())
            if empty / len(chunks) > self.max_empty_chunk_ratio:
                raise ValueError(f"Too many empty chunks: {empty}/{len(chunks)}")


class KnowledgeMCP:
    """
    Opinionated 4-step embedding pipeline MCP.

    Tools provided:
    - knowledge.embed_pipeline_run: Execute the full pipeline
    - knowledge.embed_pipeline_status: Check run status
    - knowledge.embed_pipeline_retry: Retry failed run
    - knowledge.embed_pipeline_cancel: Cancel running run

    Example:
        from gobstopper import Gobstopper
        from gobstopper.extensions.mcp import KnowledgeMCP

        app = Gobstopper(__name__)
        mcp = KnowledgeMCP(app, namespace="knowledge")

        # Register step handlers
        mcp.step(PipelineStep.INGEST)(my_ingest_handler)
        mcp.step(PipelineStep.CHUNK_EMBED)(my_embed_handler)

        # Register policies
        mcp.add_policy(TenantIsolationPolicy())
        mcp.add_policy(QualityGatePolicy())

        mcp.mount(app, path="/mcp")
    """

    def __init__(
        self,
        app=None,
        namespace: str = "knowledge",
        instructions: Optional[str] = None,
    ):
        self.namespace = namespace
        self._mcp = MCP(app, name=f"{namespace}-mcp", namespace=namespace)
        self._step_handlers: Dict[PipelineStep, StepHandler] = {}
        self._policies: List[PipelinePolicy] = []
        self._runs: Dict[str, PipelineRun] = {}

        # Register MCP tools
        self._register_tools()

    def step(self, step: PipelineStep, *, timeout: int = 300, retries: int = 2):
        """Decorator to register a step handler."""

        def decorator(handler: Callable) -> Callable:
            self._step_handlers[step] = StepHandler(
                step=step,
                handler=handler,
                timeout=timeout,
                retries=retries,
            )
            return handler

        return decorator

    def add_policy(self, policy: PipelinePolicy) -> None:
        """Add a pipeline policy."""
        self._policies.append(policy)

    def _register_tools(self) -> None:
        """Register the MCP tools."""

        @self._mcp.tool()
        async def embed_pipeline_run(
            tenant_id: str,
            partner_id: str,
            source: Dict[str, str],
            idempotency_key: str,
            options: Optional[Dict[str, Any]] = None,
            requested_by: Optional[Dict[str, str]] = None,
        ) -> Dict[str, Any]:
            """
            Run the 4-step knowledge embedding pipeline.

            Steps execute in order: INGEST → EXTRACT_NORMALIZE → CHUNK_EMBED → CONNECT_INDEX

            Args:
                tenant_id: Tenant identifier
                partner_id: Partner identifier
                source: Source document info {"kind": "...", "value": "..."}
                idempotency_key: Unique key for deduplication
                options: Pipeline options (chunk_strategy, chunk_size, embedding_model, etc.)
                requested_by: Who initiated the run {"user_id": "...", "role": "..."}
            """
            options = options or {}
            requested_by = requested_by or {}

            run = PipelineRun(
                run_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                partner_id=partner_id,
                source_kind=source.get("kind", ""),
                source_value=source.get("value", ""),
                idempotency_key=idempotency_key,
                options=options,
            )

            # Initialize step states
            for step in PipelineStep.ordered():
                run.steps[step] = StepState()

            # Check for duplicate run
            for existing_run in self._runs.values():
                if existing_run.idempotency_key == idempotency_key:
                    if existing_run.status in (RunStatus.SUCCEEDED, RunStatus.RUNNING):
                        return existing_run.to_output()

            self._runs[run.run_id] = run

            # Run pipeline
            asyncio.create_task(self._execute_pipeline(run, source, requested_by))

            return run.to_output()

        @self._mcp.tool()
        async def embed_pipeline_status(pipeline_run_id: str) -> Dict[str, Any]:
            """Get status of a pipeline run."""
            run = self._runs.get(pipeline_run_id)
            if not run:
                return {"error": f"Run not found: {pipeline_run_id}"}
            return run.to_output()

        @self._mcp.tool()
        async def embed_pipeline_retry(
            pipeline_run_id: str,
            from_step: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Retry a failed pipeline run."""
            run = self._runs.get(pipeline_run_id)
            if not run:
                return {"error": f"Run not found: {pipeline_run_id}"}

            if run.status not in (RunStatus.FAILED, RunStatus.CANCELLED):
                return {"error": f"Cannot retry run in status: {run.status}"}

            # Reset failed steps
            start_step = PipelineStep(from_step) if from_step else PipelineStep.INGEST
            for step in PipelineStep.ordered():
                if step.value == start_step.value:
                    break
                run.steps[step].status = StepStatus.SKIPPED

            for step in PipelineStep.ordered():
                if step.value == start_step.value:
                    break
                state = run.steps[step]
                if state.status == StepStatus.SKIPPED:
                    continue
                state.status = StepStatus.PENDING
                state.error = None

            run.status = RunStatus.PENDING
            asyncio.create_task(
                self._execute_pipeline(
                    run, {"kind": run.source_kind, "value": run.source_value}, {}
                )
            )

            return run.to_output()

        @self._mcp.tool()
        async def embed_pipeline_cancel(pipeline_run_id: str) -> Dict[str, Any]:
            """Cancel a running pipeline."""
            run = self._runs.get(pipeline_run_id)
            if not run:
                return {"error": f"Run not found: {pipeline_run_id}"}

            if run.status not in (RunStatus.PENDING, RunStatus.RUNNING):
                return {"error": f"Cannot cancel run in status: {run.status}"}

            run.status = RunStatus.CANCELLED
            run.completed_at = datetime.utcnow().isoformat()

            # Cancel any pending steps
            for step, state in run.steps.items():
                if state.status == StepStatus.PENDING:
                    state.status = StepStatus.SKIPPED

            return run.to_output()

    async def _execute_pipeline(
        self,
        run: PipelineRun,
        source: Dict[str, str],
        requested_by: Dict[str, str],
    ) -> None:
        """Execute the pipeline steps in order."""
        ctx = PipelineContext(
            run=run,
            step=PipelineStep.INGEST,
            tenant_id=run.tenant_id,
            partner_id=run.partner_id,
            source=source,
            options=run.options,
            requested_by=requested_by,
        )

        run.status = RunStatus.RUNNING

        # Run policies before start
        for policy in self._policies:
            await policy.before_run(ctx)

        start_time = time.time()

        # Execute steps in order
        for step in PipelineStep.ordered():
            run.current_step = step
            state = run.steps[step]
            state.status = StepStatus.RUNNING
            state.started_at = datetime.utcnow().isoformat()

            # Check if previous step succeeded
            prev = step.previous()
            if prev and run.steps[prev].status != StepStatus.SUCCEEDED:
                state.status = StepStatus.SKIPPED
                continue

            handler = self._step_handlers.get(step)
            if not handler:
                state.status = StepStatus.SKIPPED
                state.error = f"No handler registered for step: {step.value}"
                continue

            try:
                # Execute with retries
                result = await self._execute_with_retries(handler, ctx)
                state.result = result
                state.status = StepStatus.SUCCEEDED
                state.completed_at = datetime.utcnow().isoformat()

                # Run after_step policies
                step_result = StepResult(
                    output=result.output if hasattr(result, "output") else result
                )
                for policy in self._policies:
                    await policy.after_step(ctx, step, step_result)

            except Exception as e:
                state.status = StepStatus.FAILED
                state.error = str(e)
                state.completed_at = datetime.utcnow().isoformat()
                run.errors.append(f"{step.value}: {str(e)}")

                for policy in self._policies:
                    await policy.on_failure(ctx, step, str(e))

                break

        # Finalize
        elapsed_ms = (time.time() - start_time) * 1000
        run.metrics["latency_ms"] = elapsed_ms

        if run.status == RunStatus.RUNNING:
            if all(s.status == StepStatus.SUCCEEDED for s in run.steps.values()):
                run.status = RunStatus.SUCCEEDED
            elif any(s.status == StepStatus.FAILED for s in run.steps.values()):
                run.status = RunStatus.FAILED
            else:
                run.status = RunStatus.FAILED

        run.completed_at = datetime.utcnow().isoformat()

    async def _execute_with_retries(
        self, handler: StepHandler, ctx: PipelineContext
    ) -> Any:
        """Execute a step handler with retries."""
        last_error = None

        for attempt in range(handler.retries + 1):
            try:
                result = handler.handler(ctx)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as e:
                last_error = e
                ctx.run.steps[handler.step].retry_count = attempt + 1
                if attempt < handler.retries:
                    await asyncio.sleep(2**attempt)  # Exponential backoff

        raise last_error

    def mount(self, app, path: Optional[str] = None) -> None:
        """Mount MCP on the app."""
        self._mcp.mount(app, path=path)

    def run(self, transport: str = "stdio") -> None:
        """Run standalone (for Claude Desktop)."""
        self._mcp.run(transport=transport)
