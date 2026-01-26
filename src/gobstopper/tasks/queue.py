"""Task queue management for Gobstopper framework.

This module provides the core task queue system for Gobstopper, featuring:
- Priority-based task queuing with category separation
- Async worker pool management with graceful shutdown
- Automatic retry logic with exponential backoff
- Persistent storage using DuckDB (optional)
- Feature flag control via environment variable

The task system is disabled by default and must be explicitly enabled
via the WOPR_TASKS_ENABLED environment variable or constructor parameter.
This prevents accidental database creation and resource usage.

Classes:
    NoopStorage: Placeholder storage when tasks are disabled.
    TaskQueue: Main task queue with worker management and execution.

Example:
    Basic task queue usage::

        from gobstopper.tasks.queue import TaskQueue
        from gobstopper.tasks.models import TaskPriority
        import os

        # Enable tasks
        os.environ["WOPR_TASKS_ENABLED"] = "1"

        # Create queue
        queue = TaskQueue(enabled=True)

        # Register task functions
        @queue.register_task("send_email", category="notifications")
        async def send_email(to: str, subject: str):
            # Send email logic
            return {"sent": True, "to": to}

        # Start workers for category
        await queue.start_workers("notifications", worker_count=3)

        # Queue a task
        task_id = await queue.add_task(
            "send_email",
            category="notifications",
            priority=TaskPriority.HIGH,
            max_retries=3,
            "user@example.com",
            subject="Welcome!"
        )

        # Check task status
        task_info = await queue.get_task_info(task_id)
        print(f"Status: {task_info.status}")

        # Shutdown gracefully
        await queue.shutdown()

Environment Variables:
    WOPR_TASKS_ENABLED: Set to "1", "true", "True", or "yes" to enable
        the task system. Defaults to disabled.

Note:
    - Tasks are disabled by default to prevent unintended side effects
    - Storage (DuckDB) is created lazily on first use
    - Each category has its own queue and worker pool
    - Tasks within a category are ordered by priority then FIFO
    - Workers shut down gracefully, completing current tasks
"""

import asyncio
import os
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, List, Optional

from .models import TaskInfo, TaskStatus, TaskPriority

# Feature flag: tasks disabled by default unless explicitly enabled
_DEFAULT_ENABLED = os.getenv("WOPR_TASKS_ENABLED", "0") in {"1", "true", "True", "yes"}


def should_run_background_workers() -> bool:
    """Determine if background task workers should run in this process.

    When running with multiple worker processes (e.g., granian --workers 4),
    only the first/main worker process should run background task workers to
    avoid DuckDB concurrency issues and duplicate task execution.

    This function checks various environment variables set by popular ASGI
    servers to detect if this is the primary worker process:

    - Granian: GRANIAN_WORKER_ID (checks if "0")
    - Uvicorn: Not directly supported (no worker ID env var)
    - Gunicorn: GUNICORN_WORKER_ID or SERVER_SOFTWARE

    Returns:
        bool: True if background workers should run in this process, False otherwise.

    Examples:
        Check in startup handler::

            @app.on_startup
            async def startup():
                if should_run_background_workers():
                    await app.start_task_workers("default", 2)
                    await app.start_task_workers("email", 3)
                else:
                    app.logger.info("Skipping background workers (not main process)")

        Manual override for testing::

            # Force enable workers
            os.environ["WOPR_FORCE_WORKERS"] = "1"
            assert should_run_background_workers() == True

            # Force disable workers
            os.environ["WOPR_FORCE_WORKERS"] = "0"
            assert should_run_background_workers() == False

    Note:
        - Returns True if no multi-process server is detected (single process mode)
        - Can be overridden with WOPR_FORCE_WORKERS environment variable
        - Only relevant when using DuckDB storage (concurrency limitation)
        - With Redis/PostgreSQL storage, all workers can safely process tasks
    """
    # Allow explicit override for testing or special deployments
    force_workers = os.getenv("WOPR_FORCE_WORKERS")
    if force_workers is not None:
        return force_workers in {"1", "true", "True", "yes"}

    # Check Granian worker ID (most common for Gobstopper users)
    granian_worker_id = os.getenv("GRANIAN_WORKER_ID")
    if granian_worker_id is not None:
        # Only worker 0 should run background tasks
        return granian_worker_id == "0"

    # Check Gunicorn worker ID
    gunicorn_worker_id = os.getenv("GUNICORN_WORKER_ID")
    if gunicorn_worker_id is not None:
        return gunicorn_worker_id == "0"

    # Check if we're in a Gunicorn environment by looking at SERVER_SOFTWARE
    server_software = os.getenv("SERVER_SOFTWARE", "")
    if "gunicorn" in server_software.lower():
        # If we can't determine worker ID, default to not running workers
        # to be safe (avoids running on all workers)
        return False

    # Default: assume single process mode, workers should run
    return True


class NoopStorage:
    """A storage implementation that does nothing (used when tasks are disabled).

    This class provides a null-object pattern implementation of the storage
    interface, allowing the task queue to function without raising errors
    when tasks are disabled. All methods are no-ops that return safe defaults.

    This prevents database file creation and avoids import errors when
    DuckDB is not installed but tasks are disabled anyway.

    Example:
        NoopStorage is used automatically when tasks are disabled::

            queue = TaskQueue(enabled=False)
            # queue.storage will be NoopStorage()
            # No database file created, no errors raised

    Note:
        - All save operations are silently ignored
        - All query operations return None or empty lists
        - No exceptions are raised
        - Used internally by TaskQueue when enabled=False
    """
    def save_task(self, task_info: TaskInfo):
        """No-op: task is not saved."""
        return

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """No-op: always returns None."""
        return None

    def get_tasks(self, **kwargs):
        """No-op: always returns empty list."""
        return []

    def cleanup_old_tasks(self, **kwargs):
        """No-op: always returns 0 deleted."""
        return 0


class TaskQueue:
    """Priority-based background task queue with worker pool management.

    TaskQueue provides a complete async task processing system with:
    - Category-based task organization (separate queues per category)
    - Priority ordering within each category queue
    - Configurable worker pools per category
    - Automatic retry logic with exponential backoff
    - Persistent storage using DuckDB (optional)
    - Graceful shutdown with task completion
    - Task cancellation and manual retry support

    The queue system is disabled by default and must be explicitly enabled
    via environment variable (WOPR_TASKS_ENABLED=1) or constructor parameter.
    Storage is created lazily on first use to avoid unnecessary database files.

    Attributes:
        enabled: Whether the task system is enabled.
        queues: Dict mapping category names to asyncio.PriorityQueue objects.
        running_tasks: Dict of currently executing tasks by task_id.
        workers: Dict mapping category names to lists of worker tasks.
        shutdown_event: asyncio.Event signaling worker shutdown.
        task_functions: Dict mapping task names to their registered functions.

    Example:
        Complete task queue workflow::

            import asyncio
            from gobstopper.tasks.queue import TaskQueue
            from gobstopper.tasks.models import TaskPriority, TaskStatus

            # Enable and create queue
            queue = TaskQueue(enabled=True)

            # Register task functions
            @queue.register_task("send_email", category="notifications")
            async def send_email(to: str, subject: str, body: str):
                # Email sending logic
                await asyncio.sleep(1)  # Simulate work
                return {"sent": True, "to": to}

            @queue.register_task("process_data", category="analytics")
            def process_data(data: dict):  # Sync functions work too
                # Processing logic
                return {"records": len(data)}

            # Start workers
            await queue.start_workers("notifications", worker_count=3)
            await queue.start_workers("analytics", worker_count=5)

            # Queue tasks with different priorities
            task1 = await queue.add_task(
                "send_email",
                category="notifications",
                priority=TaskPriority.HIGH,
                max_retries=3,
                "user@example.com",
                subject="Welcome",
                body="Thanks for signing up!"
            )

            task2 = await queue.add_task(
                "process_data",
                category="analytics",
                priority=TaskPriority.NORMAL,
                {"users": 1000}
            )

            # Monitor task status
            while True:
                info = await queue.get_task_info(task1)
                if info.is_completed:
                    if info.status == TaskStatus.SUCCESS:
                        print(f"Result: {info.result}")
                    else:
                        print(f"Failed: {info.error}")
                    break
                await asyncio.sleep(0.5)

            # Get statistics
            stats = await queue.get_task_stats()
            print(f"Total tasks: {stats['total']}")
            print(f"Running: {stats['running']}")
            print(f"By status: {stats['by_status']}")

            # Graceful shutdown
            await queue.shutdown()

    Note:
        - Each category has its own queue and worker pool
        - Tasks are ordered by priority (descending), then FIFO
        - Both async and sync task functions are supported
        - Sync functions run in thread pool executor to avoid blocking
        - Retry delay uses exponential backoff: min(2^retry_count, 60) seconds
        - Workers complete current tasks before shutting down
    """

    def __init__(self, enabled: Optional[bool] = None, storage_factory=None):
        """Initialize a new TaskQueue.

        Args:
            enabled: Whether to enable the task system. If None, reads from
                WOPR_TASKS_ENABLED environment variable. Defaults to disabled.
            storage_factory: Optional factory function to create custom storage.
                If None, uses TaskStorage with DuckDB. Useful for testing.

        Example:
            Creating queues with different configurations::

                # Use environment variable
                import os
                os.environ["WOPR_TASKS_ENABLED"] = "1"
                queue1 = TaskQueue()  # enabled=True from env

                # Explicitly enable
                queue2 = TaskQueue(enabled=True)

                # Explicitly disable
                queue3 = TaskQueue(enabled=False)

                # Custom storage for testing
                from unittest.mock import Mock
                mock_storage = Mock()
                queue4 = TaskQueue(
                    enabled=True,
                    storage_factory=lambda: mock_storage
                )
        """
        self.enabled = _DEFAULT_ENABLED if enabled is None else enabled
        self.queues: Dict[str, asyncio.PriorityQueue] = {}
        self.running_tasks: Dict[str, TaskInfo] = {}
        self.workers: Dict[str, List[asyncio.Task]] = {}
        self.shutdown_event = asyncio.Event()
        self.task_functions: Dict[str, Callable] = {}
        # Lazy storage: created on first access only if enabled
        self._storage = None
        self._storage_factory = storage_factory
    
    @property
    def storage(self):
        """Get the storage backend, creating it lazily if needed.

        Returns NoopStorage if tasks are disabled, otherwise creates and
        caches a TaskStorage instance (or custom storage from factory).

        Returns:
            Storage object implementing save_task, get_task, get_tasks, and
            cleanup_old_tasks methods.

        Note:
            - Storage is created only on first access (lazy initialization)
            - Returns NoopStorage if enabled=False
            - Uses storage_factory if provided, otherwise creates TaskStorage
            - DuckDB is imported only when storage is actually needed
        """
        if not self.enabled:
            return NoopStorage()
        if self._storage is None:
            # Local import to avoid importing duckdb unless needed
            if self._storage_factory:
                self._storage = self._storage_factory()
            else:
                from .storage import TaskStorage  # local import
                self._storage = TaskStorage()
        return self._storage
    
    def register_task(self, name: str, category: str = "default"):
        """Decorator to register a task function with the queue.

        Registers a function (sync or async) to be available for task execution.
        The function can then be queued by name using add_task(). Both regular
        functions and coroutine functions are supported.

        Args:
            name: Unique name to identify this task function.
            category: Category for organizing tasks. Tasks in the same category
                share a queue and worker pool. Defaults to "default".

        Returns:
            Decorator function that registers and returns the original function.

        Example:
            Registering task functions::

                queue = TaskQueue(enabled=True)

                # Register async task
                @queue.register_task("send_email", category="notifications")
                async def send_email(to: str, subject: str):
                    # Async email logic
                    return {"sent": True}

                # Register sync task
                @queue.register_task("process_file", category="analytics")
                def process_file(filename: str):
                    # Sync file processing
                    return {"lines": 1000}

                # Register with default category
                @queue.register_task("cleanup")
                def cleanup():
                    # Cleanup logic
                    pass

        Note:
            - Task name must be unique across all categories
            - Category determines which queue and workers handle the task
            - Both sync and async functions are supported
            - The original function is returned unchanged (can be called directly)
        """
        def decorator(func):
            self.task_functions[name] = func
            return func
        return decorator
    
    async def add_task(self, name: str, category: str = "default",
                      priority: TaskPriority = TaskPriority.NORMAL,
                      max_retries: int = 0,
                      skip_worker_check: bool = False,
                      *args, **kwargs) -> str:
        """Add a task to the queue for execution.

        Creates a TaskInfo object with a unique ID, saves it to storage,
        and adds it to the appropriate category queue. The task will be
        picked up by a worker when available.

        Args:
            name: Name of the registered task function to execute.
            category: Category queue to add the task to. Defaults to "default".
            priority: Task priority for queue ordering. Higher priority tasks
                execute first. Defaults to TaskPriority.NORMAL.
            max_retries: Maximum number of retry attempts on failure.
                Defaults to 0 (no retries).
            *args: Positional arguments to pass to the task function.
            **kwargs: Keyword arguments to pass to the task function.

        Returns:
            str: Unique task ID (UUID4) for tracking the task.

        Raises:
            RuntimeError: If task system is disabled (enabled=False).
            ValueError: If task name is not registered.

        Example:
            Adding tasks with different configurations::

                queue = TaskQueue(enabled=True)

                # Simple task with no args
                task_id1 = await queue.add_task("cleanup")

                # Task with positional args
                task_id2 = await queue.add_task(
                    "send_email",
                    category="notifications",
                    "user@example.com",
                    "Welcome to our service"
                )

                # Task with keyword args and high priority
                task_id3 = await queue.add_task(
                    "process_order",
                    category="orders",
                    priority=TaskPriority.HIGH,
                    max_retries=3,
                    order_id=12345,
                    customer_id=67890
                )

                # Critical task with immediate execution
                task_id4 = await queue.add_task(
                    "send_alert",
                    category="alerts",
                    priority=TaskPriority.CRITICAL,
                    alert_type="security_breach"
                )

        Note:
            - Task function must be registered before adding to queue
            - Tasks are stored persistently before queueing
            - Priority queue ensures higher priority tasks execute first
            - Category queue is created automatically if it doesn't exist
            - Workers must be started for the category to process tasks
        """
        if not self.enabled:
            raise RuntimeError("TaskQueue is disabled. Set WOPR_TASKS_ENABLED=1 to enable.")

        # Check if we should queue tasks in this process
        # Only the main worker should interact with DuckDB to avoid lock conflicts
        if not skip_worker_check and not should_run_background_workers():
            raise RuntimeError(
                "Cannot queue tasks from non-main worker process due to DuckDB concurrency limitations. "
                "Tasks can only be queued from: 1) The main worker (worker ID 0), "
                "2) Single-process deployments, or 3) Applications using alternative storage backends. "
                "To queue tasks from all workers, use Redis or PostgreSQL storage instead of DuckDB."
            )

        if name not in self.task_functions:
            raise ValueError(f"Task '{name}' not registered")
        
        task_info = TaskInfo(
            id=str(uuid.uuid4()), name=name, category=category,
            priority=priority, status=TaskStatus.PENDING,
            created_at=datetime.now(), max_retries=max_retries,
            args=args, kwargs=kwargs
        )
        
        self.storage.save_task(task_info)
        
        if category not in self.queues:
            self.queues[category] = asyncio.PriorityQueue()
        
        await self.queues[category].put((-priority.value, task_info.id, task_info))
        return task_info.id
    
    async def get_task_info(self, task_id: str) -> Optional[TaskInfo]:
        """Retrieve task information and current status.

        Checks running tasks first (in-memory), then queries storage for
        completed or pending tasks. Provides real-time task status.

        Args:
            task_id: Unique identifier of the task to retrieve.

        Returns:
            TaskInfo object if found, None if task doesn't exist or
            tasks are disabled.

        Example:
            Monitoring task progress::

                task_id = await queue.add_task("long_process")

                # Poll for completion
                while True:
                    info = await queue.get_task_info(task_id)
                    if info:
                        print(f"Status: {info.status.value}")
                        print(f"Progress: {info.progress}%")
                        print(f"Message: {info.progress_message}")

                        if info.is_completed:
                            if info.status == TaskStatus.SUCCESS:
                                print(f"Result: {info.result}")
                                print(f"Duration: {info.elapsed_seconds}s")
                            else:
                                print(f"Error: {info.error}")
                            break
                    await asyncio.sleep(1)

        Note:
            - Returns None if tasks are disabled
            - Checks running tasks first for immediate status
            - Falls back to storage for persistent lookup
            - Real-time progress tracking if task updates progress field
        """
        if not self.enabled:
            return None
        # Check running tasks first
        if task_id in self.running_tasks:
            return self.running_tasks[task_id]
        
        # Check storage
        return self.storage.get_task(task_id)
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task before execution.

        Marks a task as CANCELLED if it's still pending. Cannot cancel
        tasks that are already running or completed.

        Args:
            task_id: Unique identifier of the task to cancel.

        Returns:
            bool: True if task was successfully cancelled, False if task
                doesn't exist, is not pending, or tasks are disabled.

        Example:
            Cancelling tasks conditionally::

                # Queue a low priority task
                task_id = await queue.add_task(
                    "generate_report",
                    priority=TaskPriority.LOW
                )

                # Later, decide to cancel it
                if await queue.cancel_task(task_id):
                    print("Task cancelled successfully")
                else:
                    print("Task already started or completed")

        Note:
            - Only PENDING tasks can be cancelled
            - Running tasks cannot be cancelled this way
            - Cancelled tasks are marked with completed_at timestamp
            - Returns False if tasks are disabled
        """
        if not self.enabled:
            return False
        task_info = await self.get_task_info(task_id)
        if not task_info:
            return False
        
        if task_info.status == TaskStatus.PENDING:
            task_info.status = TaskStatus.CANCELLED
            task_info.completed_at = datetime.now()
            self.storage.save_task(task_info)
            return True
        
        return False
    
    async def retry_task(self, task_id: str) -> bool:
        """Manually retry a failed task.

        Resets a failed task's status and requeues it for execution.
        Useful for retrying tasks that failed due to transient issues
        after the automatic retry limit was reached.

        Args:
            task_id: Unique identifier of the task to retry.

        Returns:
            bool: True if task was successfully requeued, False if task
                doesn't exist, is not failed, or tasks are disabled.

        Example:
            Manual retry after investigation::

                # Check failed task
                task = await queue.get_task_info(task_id)
                if task and task.status == TaskStatus.FAILED:
                    print(f"Task failed: {task.error}")

                    # Fix underlying issue (e.g., restore network)
                    # ...

                    # Retry the task
                    if await queue.retry_task(task_id):
                        print("Task requeued for retry")
                    else:
                        print("Could not retry task")

        Note:
            - Only FAILED tasks can be manually retried
            - Resets task status to PENDING
            - Clears error, timing, and progress information
            - Does not increment retry_count
            - Task is added back to its original category queue
            - Returns False if tasks are disabled
        """
        if not self.enabled:
            return False
        task_info = await self.get_task_info(task_id)
        if not task_info or task_info.status != TaskStatus.FAILED:
            return False
        
        # Reset task status and re-queue
        task_info.status = TaskStatus.PENDING
        task_info.started_at = None
        task_info.completed_at = None
        task_info.error = None
        task_info.progress = 0.0
        task_info.progress_message = ""
        
        self.storage.save_task(task_info)
        
        if task_info.category not in self.queues:
            self.queues[task_info.category] = asyncio.PriorityQueue()
        
        await self.queues[task_info.category].put(
            (-task_info.priority.value, task_info.id, task_info)
        )
        return True
    
    async def get_task_stats(self) -> dict:
        """Get aggregate statistics about tasks across all categories.

        Queries storage for recent tasks and computes statistics including
        counts by status, counts by category, running tasks, and queued tasks.

        Returns:
            dict: Statistics dictionary with keys:
                - total: Total number of tasks in storage (up to 1000 recent)
                - by_status: Dict mapping status values to counts
                - by_category: Dict mapping category names to counts
                - running: Number of currently executing tasks
                - queued: Number of tasks waiting in all queues

        Example:
            Monitoring queue health::

                stats = await queue.get_task_stats()

                print(f"Total tasks: {stats['total']}")
                print(f"Currently running: {stats['running']}")
                print(f"Queued: {stats['queued']}")

                print("\nBy status:")
                for status, count in stats['by_status'].items():
                    print(f"  {status}: {count}")

                print("\nBy category:")
                for category, count in stats['by_category'].items():
                    print(f"  {category}: {count}")

        Note:
            - Returns zero/empty stats if tasks are disabled
            - Limited to 1000 most recent tasks for performance
            - by_status uses status string values, not enums
            - running count is from in-memory tracking
            - queued count is sum of all category queues
        """
        if not self.enabled:
            return {"total": 0, "by_status": {}, "by_category": {}, "running": 0, "queued": 0}
        all_tasks = self.storage.get_tasks(limit=1000)  # Get recent tasks
        
        stats = {
            "total": len(all_tasks),
            "by_status": defaultdict(int),
            "by_category": defaultdict(int),
            "running": len(self.running_tasks),
            "queued": sum(queue.qsize() for queue in self.queues.values())
        }
        
        for task in all_tasks:
            stats["by_status"][task.status.value] += 1
            stats["by_category"][task.category] += 1
        
        return dict(stats)
    
    async def start_workers(self, category: str, worker_count: int = 1):
        """Start worker tasks to process tasks in a category queue.

        Creates and starts async worker tasks that continuously poll the
        category queue and execute tasks. Workers run until shutdown is
        called or they are cancelled.

        Args:
            category: Name of the category queue to start workers for.
            worker_count: Number of worker tasks to create. Defaults to 1.

        Example:
            Starting workers for different workloads::

                queue = TaskQueue(enabled=True)

                # Start 3 workers for email notifications
                await queue.start_workers("notifications", worker_count=3)

                # Start 10 workers for heavy processing
                await queue.start_workers("analytics", worker_count=10)

                # Start 1 worker for low-volume admin tasks
                await queue.start_workers("admin", worker_count=1)

                # Now tasks in these categories will be processed

        Note:
            - Does nothing if tasks are disabled
            - Category queue is created automatically if needed
            - Workers are tracked in self.workers[category]
            - Multiple calls add more workers to existing pool
            - Workers process tasks by priority, then FIFO
            - Each worker handles one task at a time
            - Workers shut down gracefully on queue.shutdown()
        """
        if not self.enabled:
            return
        if category not in self.workers:
            self.workers[category] = []
        
        for i in range(worker_count):
            worker = asyncio.create_task(self._worker(category, i))
            self.workers[category].append(worker)
    
    async def shutdown(self):
        """Shutdown all workers gracefully, completing current tasks.

        Sets the shutdown event, cancels all worker tasks, and waits for
        them to finish their current task and exit. Ensures clean shutdown
        without leaving tasks in inconsistent states.

        Example:
            Graceful application shutdown::

                queue = TaskQueue(enabled=True)

                # Register tasks and start workers
                # ...

                try:
                    # Run application
                    await app.run()
                finally:
                    # Ensure workers shut down cleanly
                    await queue.shutdown()
                    print("All workers stopped")

        Note:
            - Does nothing if tasks are disabled
            - Sets shutdown_event to signal workers to stop
            - Cancels all worker tasks across all categories
            - Waits for workers to complete current task execution
            - Safe to call multiple times (idempotent)
            - Exceptions during worker shutdown are suppressed
        """
        if not self.enabled:
            return
        self.shutdown_event.set()
        
        # Cancel all workers
        for workers in self.workers.values():
            for worker in workers:
                worker.cancel()
        
        # Wait for workers to finish
        for workers in self.workers.values():
            await asyncio.gather(*workers, return_exceptions=True)
    
    async def _worker(self, category: str, worker_id: int):
        """Worker coroutine that continuously processes tasks from a category queue.

        Internal method that runs in a loop, polling the category queue for
        tasks and executing them. Handles queue timeouts, shutdown signals,
        and exceptions during task execution.

        Args:
            category: Name of the category queue to process tasks from.
            worker_id: Unique identifier for this worker within the category.

        Note:
            - Internal method, not meant to be called directly
            - Created and managed by start_workers()
            - Runs until shutdown_event is set or worker is cancelled
            - Polls queue with 1-second timeout to check shutdown periodically
            - Delegates actual task execution to _execute_task()
            - Prints errors to stdout (should use logging in production)
            - Exits cleanly on CancelledError

        Worker Lifecycle:
            1. Wait for task from queue (with 1s timeout)
            2. If timeout, check shutdown event and loop
            3. If task received, execute it via _execute_task()
            4. Handle any exceptions and continue
            5. Exit when shutdown_event is set or cancelled
        """
        if category not in self.queues:
            self.queues[category] = asyncio.PriorityQueue()
        
        queue = self.queues[category]
        
        while not self.shutdown_event.is_set():
            try:
                try:
                    priority, task_id, task_info = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                await self._execute_task(task_info)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Worker {category}-{worker_id} error: {e}")
    
    async def _execute_task(self, task_info: TaskInfo):
        """Execute a single task with retry logic and error handling.

        Internal method that handles the complete task execution lifecycle:
        - Updates status to STARTED and saves to storage
        - Executes the task function (async or sync)
        - Handles success, failure, and retry logic
        - Updates timing and progress information
        - Implements exponential backoff for retries

        Args:
            task_info: TaskInfo object containing task metadata and parameters.

        Task Execution Flow:
            1. Verify task function is registered
            2. Mark task as STARTED, save to storage
            3. Add to running_tasks dict for tracking
            4. Execute task function with provided args/kwargs
            5. On success:
               - Mark as SUCCESS
               - Store result
               - Set elapsed time and 100% progress
            6. On failure:
               - Increment retry_count
               - If retries remaining:
                 - Mark as RETRY
                 - Sleep with exponential backoff
                 - Requeue task
               - If retries exhausted:
                 - Mark as FAILED
                 - Set elapsed time
            7. Remove from running_tasks
            8. Save final state to storage

        Retry Logic:
            - Retries only if retry_count <= max_retries
            - Backoff delay: min(2^retry_count, 60) seconds
            - Examples:
              - 1st retry: 2 seconds
              - 2nd retry: 4 seconds
              - 3rd retry: 8 seconds
              - 6th+ retry: 60 seconds (capped)

        Note:
            - Internal method, called by workers
            - Handles both async and sync task functions
            - Sync functions run in thread pool executor
            - All state changes are persisted to storage
            - Running tasks tracked in-memory for quick lookup
            - Task function not found is treated as immediate failure
        """
        task_func = self.task_functions.get(task_info.name)
        if not task_func:
            task_info.status = TaskStatus.FAILED
            task_info.error = f"Task function '{task_info.name}' not found"
            task_info.completed_at = datetime.now()
            self.storage.save_task(task_info)
            return
        
        task_info.status = TaskStatus.STARTED
        task_info.started_at = datetime.now()
        self.running_tasks[task_info.id] = task_info
        self.storage.save_task(task_info)
        
        try:
            if asyncio.iscoroutinefunction(task_func):
                result = await task_func(*task_info.args, **task_info.kwargs)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, lambda: task_func(*task_info.args, **task_info.kwargs))
            
            task_info.status = TaskStatus.SUCCESS
            task_info.result = result
            task_info.completed_at = datetime.now()
            task_info.elapsed_seconds = (task_info.completed_at - task_info.started_at).total_seconds()
            task_info.progress = 100.0
            
        except Exception as e:
            task_info.error = str(e)
            task_info.retry_count += 1
            
            if task_info.retry_count <= task_info.max_retries:
                task_info.status = TaskStatus.RETRY
                await asyncio.sleep(min(2 ** task_info.retry_count, 60))
                queue = self.queues[task_info.category]
                await queue.put((-task_info.priority.value, task_info.id, task_info))
            else:
                task_info.status = TaskStatus.FAILED
                task_info.completed_at = datetime.now()
                task_info.elapsed_seconds = (task_info.completed_at - task_info.started_at).total_seconds()
        
        finally:
            # Save to storage BEFORE removing from running_tasks to avoid race condition
            # where get_task_info() checks running_tasks (not found) then storage (not yet saved)
            self.storage.save_task(task_info)
            if task_info.id in self.running_tasks:
                del self.running_tasks[task_info.id]