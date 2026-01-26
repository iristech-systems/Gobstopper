"""Task data models for Gobstopper framework.

This module provides the core data models and enums for the Gobstopper task system,
including task status tracking, priority levels, and comprehensive metadata.

The models are implemented using msgspec.Struct for high performance serialization
and deserialization, making them suitable for storage in DuckDB and efficient
memory usage.

Classes:
    TaskStatus: Enumeration of all possible task execution states.
    TaskPriority: Enumeration of task priority levels for queue ordering.
    TaskInfo: Complete task metadata and execution state tracking.

Example:
    Creating a task info object for tracking::

        from datetime import datetime
        from gobstopper.tasks.models import TaskInfo, TaskStatus, TaskPriority

        task = TaskInfo(
            id="task-123",
            name="send_email",
            category="notifications",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            args=("user@example.com",),
            kwargs={"subject": "Welcome", "template": "welcome.html"}
        )

Note:
    All datetime fields use timezone-naive datetime objects. It's recommended
    to use UTC for consistency across distributed systems.
"""

from msgspec import Struct, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TaskStatus(Enum):
    """Task execution status enumeration.

    Tracks the lifecycle state of a task from creation through completion.
    Tasks progress through these states as they are queued, executed, and
    finalized.

    Attributes:
        PENDING: Task is queued and waiting to be picked up by a worker.
        STARTED: Task is currently being executed by a worker.
        SUCCESS: Task completed successfully without errors.
        FAILED: Task failed and exceeded its retry limit.
        CANCELLED: Task was explicitly cancelled before execution.
        RETRY: Task failed but will be retried (transient state).

    Example:
        Checking task status::

            if task.status == TaskStatus.PENDING:
                print("Task is waiting in queue")
            elif task.status == TaskStatus.STARTED:
                print(f"Task is running: {task.progress}% complete")
            elif task.status == TaskStatus.SUCCESS:
                print(f"Task completed in {task.elapsed_seconds}s")

    Note:
        RETRY is a transient state - tasks in RETRY status are automatically
        requeued as PENDING after an exponential backoff delay.
    """
    PENDING = "pending"
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"


class TaskPriority(Enum):
    """Task priority levels for queue ordering.

    Higher priority tasks are executed before lower priority tasks within
    the same category queue. Priority values determine the execution order
    in the priority queue.

    Attributes:
        LOW: Low priority (1) - for non-urgent background tasks.
        NORMAL: Normal priority (2) - default for most tasks.
        HIGH: High priority (3) - for time-sensitive operations.
        CRITICAL: Critical priority (4) - for urgent, must-run-first tasks.

    Example:
        Setting task priority::

            # Regular background cleanup
            await queue.add_task(
                "cleanup_temp_files",
                priority=TaskPriority.LOW
            )

            # User-initiated email
            await queue.add_task(
                "send_email",
                priority=TaskPriority.HIGH,
                args=("user@example.com",)
            )

            # System alert notification
            await queue.add_task(
                "send_alert",
                priority=TaskPriority.CRITICAL,
                kwargs={"alert_type": "security"}
            )

    Note:
        Tasks with the same priority are processed in FIFO order.
        Priority only affects ordering within a category queue.
    """
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class TaskInfo(Struct, kw_only=True):
    """Complete task metadata and execution state tracking.

    Stores all information about a task from creation through completion,
    including timing data, execution results, error information, and progress
    tracking. Uses msgspec.Struct for efficient serialization and memory usage.

    Attributes:
        id: Unique task identifier (UUID4 string).
        name: Name of the registered task function to execute.
        category: Category queue this task belongs to (e.g., "email", "reports").
        priority: Task priority level determining execution order.
        status: Current execution state of the task.
        created_at: Timestamp when the task was created and queued.
        started_at: Timestamp when worker began executing (None if not started).
        completed_at: Timestamp when execution finished (None if not complete).
        elapsed_seconds: Total execution time in seconds (0.0 if not complete).
        result: Return value from the task function (None if no return value).
        error: Error message if task failed (None if successful).
        retry_count: Number of retry attempts made so far.
        max_retries: Maximum number of retries allowed before marking as FAILED.
        args: Positional arguments passed to the task function.
        kwargs: Keyword arguments passed to the task function.
        progress: Completion percentage (0.0 to 100.0) for progress tracking.
        progress_message: Human-readable progress status message.

    Example:
        Creating and tracking a task::

            from datetime import datetime
            from gobstopper.tasks.models import TaskInfo, TaskStatus, TaskPriority

            # Create task info when queuing
            task = TaskInfo(
                id="550e8400-e29b-41d4-a716-446655440000",
                name="send_welcome_email",
                category="notifications",
                priority=TaskPriority.HIGH,
                status=TaskStatus.PENDING,
                created_at=datetime.now(),
                max_retries=3,
                args=("user@example.com",),
                kwargs={
                    "template": "welcome.html",
                    "language": "en"
                }
            )

            # Update progress during execution
            task.progress = 50.0
            task.progress_message = "Rendering email template..."

            # Mark completion
            task.status = TaskStatus.SUCCESS
            task.completed_at = datetime.now()
            task.elapsed_seconds = 2.5
            task.progress = 100.0

    Note:
        - All datetime fields are timezone-naive; use UTC for consistency.
        - TaskInfo instances are stored in DuckDB for persistence.
        - The result field can store any JSON-serializable data.
        - Progress tracking is optional; tasks work fine with progress=0.0.
    """
    id: str
    name: str
    category: str
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_seconds: float = 0.0
    result: Any = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 0
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    progress: float = 0.0
    progress_message: str = ""
    
    @property
    def is_running(self) -> bool:
        """Check if the task is currently being executed.

        Returns:
            bool: True if task status is STARTED, False otherwise.

        Example:
            Monitoring task execution::

                task_info = await queue.get_task_info(task_id)
                if task_info.is_running:
                    print(f"Task is {task_info.progress}% complete")
                    print(f"Status: {task_info.progress_message}")
        """
        return self.status == TaskStatus.STARTED

    @property
    def is_completed(self) -> bool:
        """Check if the task has reached a terminal state.

        A task is considered completed if it has reached SUCCESS, FAILED,
        or CANCELLED status. These are terminal states where no further
        execution will occur.

        Returns:
            bool: True if task is in a terminal state, False if still
                pending, running, or eligible for retry.

        Example:
            Waiting for task completion::

                while True:
                    task_info = await queue.get_task_info(task_id)
                    if task_info.is_completed:
                        if task_info.status == TaskStatus.SUCCESS:
                            print(f"Result: {task_info.result}")
                        else:
                            print(f"Error: {task_info.error}")
                        break
                    await asyncio.sleep(1)

        Note:
            RETRY status is not considered completed - the task will be
            requeued automatically.
        """
        return self.status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED)