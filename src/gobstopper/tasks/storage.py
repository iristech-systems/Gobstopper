"""Task storage with DuckDB backend for Gobstopper framework.

This module provides persistent storage for task metadata using DuckDB,
an embedded analytical database. Tasks are stored with full metadata including
status, timing, results, and error information for tracking and debugging.

The storage system features:
- Lazy database initialization (no file created until first use)
- Automatic table and index creation
- Efficient querying with category and status filters
- Intelligent cleanup of old completed tasks
- JSON serialization for complex data types

Classes:
    TaskStorage: DuckDB-based persistent task storage with indexing.

Example:
    Basic storage operations::

        from gobstopper.tasks.storage import TaskStorage
        from gobstopper.tasks.models import TaskInfo, TaskStatus, TaskPriority
        from datetime import datetime

        # Create storage instance
        storage = TaskStorage("my_tasks.duckdb")

        # Save a task
        task = TaskInfo(
            id="task-123",
            name="process_data",
            category="analytics",
            priority=TaskPriority.NORMAL,
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        storage.save_task(task)

        # Retrieve task
        retrieved = storage.get_task("task-123")
        print(f"Status: {retrieved.status}")

        # Query by category
        analytics_tasks = storage.get_tasks(category="analytics", limit=50)

        # Cleanup old completed tasks
        deleted = storage.cleanup_old_tasks(days=30)
        print(f"Deleted {deleted} old tasks")

Note:
    DuckDB is required for task storage. Install with: uv add duckdb
    The database file is created lazily on first use.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Union
import msgspec

from .models import TaskInfo, TaskStatus, TaskPriority

try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


class TaskStorage:
    """DuckDB-based task storage with intelligent cleanup.

    Provides persistent storage for TaskInfo objects using DuckDB as the backend.
    The database is created lazily on first use, with automatic schema creation
    and index optimization for common query patterns.

    The storage layer handles:
    - Conversion between TaskInfo objects and database rows
    - JSON serialization of complex fields (args, kwargs, result)
    - Datetime string conversion for database compatibility
    - Efficient indexing on category, status, created_at, and priority
    - Safe concurrent access through DuckDB's transaction handling

    Attributes:
        db_path: Path to the DuckDB database file.
        connection: DuckDB connection object (created lazily).

    Example:
        Creating and using storage::

            from gobstopper.tasks.storage import TaskStorage
            from gobstopper.tasks.models import TaskInfo, TaskStatus, TaskPriority
            from datetime import datetime

            # Initialize storage (no database file created yet)
            storage = TaskStorage("tasks.duckdb")

            # Create and save a task
            task = TaskInfo(
                id="550e8400-e29b-41d4-a716-446655440000",
                name="send_email",
                category="notifications",
                priority=TaskPriority.HIGH,
                status=TaskStatus.PENDING,
                created_at=datetime.now(),
                args=("user@example.com",),
                kwargs={"subject": "Welcome"}
            )
            storage.save_task(task)  # Database file created here

            # Update task status
            task.status = TaskStatus.SUCCESS
            task.completed_at = datetime.now()
            storage.save_task(task)  # Updates existing record

            # Query tasks
            pending = storage.get_tasks(status=TaskStatus.PENDING, limit=100)
            email_tasks = storage.get_tasks(category="notifications")

    Raises:
        ImportError: If DuckDB is not installed.

    Note:
        - Database initialization is deferred until first actual use
        - The database file is created with full schema on first write
        - All datetime values are stored as ISO 8601 strings
        - JSON fields (args, kwargs, result) support any JSON-serializable data
    """

    def __init__(self, db_path: Union[str, Path] = "gobstopper_tasks.duckdb"):
        """Initialize TaskStorage with a database path.

        Args:
            db_path: Path to the DuckDB database file. Can be relative or
                absolute. Defaults to "gobstopper_tasks.duckdb" in current directory.

        Raises:
            ImportError: If DuckDB package is not installed.

        Note:
            The database file is not created until the first operation that
            requires it. This allows TaskStorage to be instantiated without
            side effects.
        """
        if not DUCKDB_AVAILABLE:
            raise ImportError(
                "DuckDB is required for task storage. Install: uv add duckdb"
            )

        self.db_path = Path(db_path)
        self.connection = None  # Lazy connection; do not touch DB until first use

    def _init_database(self):
        """Initialize database connection, schema, and indexes.

        Creates the DuckDB connection and sets up the tasks table with all
        necessary columns and indexes. This method is called automatically
        on the first database operation (lazy initialization).

        The tasks table includes:
        - Primary key on id (UUID)
        - Columns for all TaskInfo fields
        - JSON columns for args, kwargs, and result
        - Indexes on category, status, created_at, and priority

        Note:
            This method is idempotent - calling it multiple times is safe.
            If the connection already exists, it returns immediately.
            Uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.
        """
        if self.connection is not None:
            return
        # Use read_write mode explicitly to allow better error messages
        # For multi-process deployments, consider using shared database access
        # or an alternative storage backend (Redis/PostgreSQL)
        try:
            self.connection = duckdb.connect(str(self.db_path))
        except Exception as e:
            # Re-raise with more helpful message
            raise RuntimeError(
                f"Failed to open DuckDB task storage at {self.db_path}. "
                "If running with multiple workers, DuckDB may have lock conflicts. "
                "Consider: 1) Using should_run_background_workers() to limit task access, "
                "2) Using a shared storage backend (Redis/PostgreSQL), or "
                "3) Running with a single worker process."
            ) from e

        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id VARCHAR PRIMARY KEY,
                name VARCHAR NOT NULL,
                category VARCHAR NOT NULL,
                priority INTEGER NOT NULL,
                status VARCHAR NOT NULL,
                created_at TIMESTAMP NOT NULL,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                elapsed_seconds DOUBLE,
                result JSON,
                error TEXT,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 0,
                attempt INTEGER DEFAULT 0,
                max_attempts INTEGER DEFAULT 1,
                idempotency_key VARCHAR,
                not_before TIMESTAMP,
                next_attempt_at TIMESTAMP,
                lease_owner VARCHAR,
                lease_expires_at TIMESTAMP,
                claimed_at TIMESTAMP,
                last_heartbeat_at TIMESTAMP,
                args JSON,
                kwargs JSON,
                progress DOUBLE DEFAULT 0.0,
                progress_message VARCHAR DEFAULT ''
            )
        """)

        # Create indexes for performance
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_tasks_category ON tasks(category)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_next_attempt ON tasks(next_attempt_at)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_idempotency_key ON tasks(idempotency_key)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_lease_expires ON tasks(lease_expires_at)",
        ]
        for idx in indexes:
            self.connection.execute(idx)

        # Best-effort additive migration for existing databases
        migrations = [
            "ALTER TABLE tasks ADD COLUMN attempt INTEGER DEFAULT 0",
            "ALTER TABLE tasks ADD COLUMN max_attempts INTEGER DEFAULT 1",
            "ALTER TABLE tasks ADD COLUMN idempotency_key VARCHAR",
            "ALTER TABLE tasks ADD COLUMN not_before TIMESTAMP",
            "ALTER TABLE tasks ADD COLUMN next_attempt_at TIMESTAMP",
            "ALTER TABLE tasks ADD COLUMN lease_owner VARCHAR",
            "ALTER TABLE tasks ADD COLUMN lease_expires_at TIMESTAMP",
            "ALTER TABLE tasks ADD COLUMN claimed_at TIMESTAMP",
            "ALTER TABLE tasks ADD COLUMN last_heartbeat_at TIMESTAMP",
        ]
        for ddl in migrations:
            try:
                self.connection.execute(ddl)
            except Exception:
                pass

    def save_task(self, task_info: TaskInfo):
        """Save or update task information in the database.

        Performs an upsert operation (INSERT OR REPLACE) to either create
        a new task record or update an existing one. All TaskInfo fields
        are serialized appropriately for database storage.

        Args:
            task_info: TaskInfo object to save or update.

        Example:
            Saving and updating a task::

                task = TaskInfo(
                    id="task-123",
                    name="process_data",
                    category="analytics",
                    priority=TaskPriority.NORMAL,
                    status=TaskStatus.PENDING,
                    created_at=datetime.now()
                )

                # Initial save
                storage.save_task(task)

                # Update after execution
                task.status = TaskStatus.SUCCESS
                task.completed_at = datetime.now()
                task.elapsed_seconds = 5.2
                task.result = {"records_processed": 1000}
                storage.save_task(task)  # Updates existing record

        Note:
            - Datetime objects are converted to ISO 8601 strings
            - TaskPriority and TaskStatus enums are stored as their values
            - args, kwargs, and result are JSON-serialized
            - The database is initialized automatically if needed
        """
        self._init_database()
        # Convert msgspec.Struct to dict (TaskInfo is not a dataclass)
        task_dict = msgspec.structs.asdict(task_info)

        # Convert datetime objects to ISO strings
        for key in [
            "created_at",
            "started_at",
            "completed_at",
            "not_before",
            "next_attempt_at",
            "lease_expires_at",
            "claimed_at",
            "last_heartbeat_at",
        ]:
            if task_dict[key]:
                task_dict[key] = task_dict[key].isoformat()

        task_dict["priority"] = task_info.priority.value
        task_dict["status"] = task_info.status.value
        task_dict["args"] = json.dumps(task_dict["args"])
        task_dict["kwargs"] = json.dumps(task_dict["kwargs"])
        task_dict["result"] = json.dumps(task_dict["result"])

        values_tuple = tuple(task_dict.values())

        # Use explicit INSERT with ON CONFLICT to properly update all columns
        # INSERT OR REPLACE was not updating columns correctly in DuckDB
        self.connection.execute(
            """
            INSERT INTO tasks (
                id, name, category, priority, status, created_at, started_at, completed_at,
                elapsed_seconds, result, error, retry_count, max_retries,
                attempt, max_attempts, idempotency_key, not_before, next_attempt_at,
                lease_owner, lease_expires_at, claimed_at, last_heartbeat_at,
                args, kwargs, progress, progress_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                priority = EXCLUDED.priority,
                status = EXCLUDED.status,
                created_at = EXCLUDED.created_at,
                started_at = EXCLUDED.started_at,
                completed_at = EXCLUDED.completed_at,
                elapsed_seconds = EXCLUDED.elapsed_seconds,
                result = EXCLUDED.result,
                error = EXCLUDED.error,
                retry_count = EXCLUDED.retry_count,
                max_retries = EXCLUDED.max_retries,
                attempt = EXCLUDED.attempt,
                max_attempts = EXCLUDED.max_attempts,
                idempotency_key = EXCLUDED.idempotency_key,
                not_before = EXCLUDED.not_before,
                next_attempt_at = EXCLUDED.next_attempt_at,
                lease_owner = EXCLUDED.lease_owner,
                lease_expires_at = EXCLUDED.lease_expires_at,
                claimed_at = EXCLUDED.claimed_at,
                last_heartbeat_at = EXCLUDED.last_heartbeat_at,
                args = EXCLUDED.args,
                kwargs = EXCLUDED.kwargs,
                progress = EXCLUDED.progress,
                progress_message = EXCLUDED.progress_message
        """,
            values_tuple,
        )
        # Explicitly commit the transaction to ensure changes are persisted
        self.connection.commit()

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Retrieve a single task by its unique ID.

        Args:
            task_id: Unique identifier of the task to retrieve.

        Returns:
            TaskInfo object if found, None if no task exists with that ID.

        Example:
            Retrieving and checking a task::

                task = storage.get_task("550e8400-e29b-41d4-a716-446655440000")
                if task:
                    print(f"Task: {task.name}")
                    print(f"Status: {task.status.value}")
                    if task.status == TaskStatus.SUCCESS:
                        print(f"Result: {task.result}")
                else:
                    print("Task not found")

        Note:
            Returns None rather than raising an exception if task doesn't exist.
        """
        self._init_database()
        result = self.connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()

        return self._row_to_task_info(result) if result else None

    def get_tasks(
        self,
        category: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[TaskInfo]:
        """Query tasks with optional filtering and pagination.

        Retrieves multiple tasks from storage with optional filters on category
        and status. Results are ordered by creation time (newest first) and
        support pagination via limit/offset.

        Args:
            category: Filter by task category (e.g., "email", "reports").
                If None, returns tasks from all categories.
            status: Filter by TaskStatus enum value. If None, returns tasks
                in any status.
            limit: Maximum number of tasks to return. Defaults to 100.
            offset: Number of tasks to skip (for pagination). Defaults to 0.

        Returns:
            List of TaskInfo objects matching the filters, ordered by
            created_at DESC (newest first). Empty list if no matches.

        Example:
            Querying tasks with filters::

                # Get all pending email tasks
                pending_emails = storage.get_tasks(
                    category="email",
                    status=TaskStatus.PENDING,
                    limit=50
                )

                # Get next page of results
                next_page = storage.get_tasks(
                    category="email",
                    status=TaskStatus.PENDING,
                    limit=50,
                    offset=50
                )

                # Get recent failed tasks across all categories
                failed = storage.get_tasks(
                    status=TaskStatus.FAILED,
                    limit=20
                )

                # Get all tasks in analytics category
                analytics = storage.get_tasks(category="analytics")

        Note:
            - Results are always ordered by created_at DESC
            - Efficient queries due to indexes on category and status
            - Both category and status filters are optional
        """
        self._init_database()
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        results = self.connection.execute(query, params).fetchall()
        return [self._row_to_task_info(row) for row in results]

    def get_task_by_idempotency_key(self, idempotency_key: str) -> Optional[TaskInfo]:
        """Return most recent task matching idempotency key."""
        self._init_database()
        row = self.connection.execute(
            "SELECT * FROM tasks WHERE idempotency_key = ? ORDER BY created_at DESC LIMIT 1",
            (idempotency_key,),
        ).fetchone()
        return self._row_to_task_info(row) if row else None

    def claim_next(
        self,
        category: str,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> Optional[TaskInfo]:
        """Claim the next ready task for a worker lease window."""
        self._init_database()
        now_iso = now.isoformat()
        lease_expires = (now + timedelta(seconds=lease_seconds)).isoformat()

        self.connection.execute("BEGIN TRANSACTION")
        try:
            row = self.connection.execute(
                """
                SELECT id
                FROM tasks
                WHERE category = ?
                  AND status IN ('pending', 'retry')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                  AND (not_before IS NULL OR not_before <= ?)
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                ORDER BY COALESCE(next_attempt_at, not_before, created_at) ASC,
                         priority DESC,
                         created_at ASC
                LIMIT 1
                """,
                (category, now_iso, now_iso, now_iso),
            ).fetchone()

            if not row:
                self.connection.execute("COMMIT")
                return None

            task_id = row[0]
            self.connection.execute(
                """
                UPDATE tasks
                SET status = 'started',
                    attempt = COALESCE(attempt, 0) + 1,
                    lease_owner = ?,
                    lease_expires_at = ?,
                    claimed_at = COALESCE(claimed_at, ?),
                    last_heartbeat_at = ?,
                    started_at = ?,
                    next_attempt_at = NULL
                WHERE id = ?
                  AND status IN ('pending', 'retry')
                  AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
                """,
                (
                    worker_id,
                    lease_expires,
                    now_iso,
                    now_iso,
                    now_iso,
                    task_id,
                    now_iso,
                ),
            )

            claimed = self.connection.execute(
                "SELECT * FROM tasks WHERE id = ? AND lease_owner = ?",
                (task_id, worker_id),
            ).fetchone()

            self.connection.execute("COMMIT")
            return self._row_to_task_info(claimed) if claimed else None
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    def renew_lease(
        self,
        task_id: str,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> bool:
        """Extend lease for an in-flight task owned by worker."""
        self._init_database()
        now_iso = now.isoformat()
        lease_expires = (now + timedelta(seconds=lease_seconds)).isoformat()
        self.connection.execute(
            """
            UPDATE tasks
            SET lease_expires_at = ?, last_heartbeat_at = ?
            WHERE id = ? AND lease_owner = ? AND status = 'started'
            """,
            (lease_expires, now_iso, task_id, worker_id),
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT 1 FROM tasks WHERE id = ? AND lease_owner = ? AND status = 'started'",
            (task_id, worker_id),
        ).fetchone()
        return row is not None

    def reclaim_expired_leases(self, now: datetime, limit: int = 1000) -> int:
        """Move expired STARTED tasks back to RETRY."""
        self._init_database()
        now_iso = now.isoformat()
        result = self.connection.execute(
            """
            UPDATE tasks
            SET status = 'retry',
                lease_owner = NULL,
                lease_expires_at = NULL,
                last_heartbeat_at = NULL,
                next_attempt_at = ?
            WHERE id IN (
                SELECT id FROM tasks
                WHERE status = 'started'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at < ?
                LIMIT ?
            )
            """,
            (now_iso, now_iso, limit),
        )
        self.connection.commit()
        return max(0, result.rowcount)

    def cleanup_old_tasks(
        self, days: int = None, months: int = None, years: int = None
    ):
        """Delete old completed tasks to manage database size.

        Removes tasks that completed before a calculated cutoff date. Only
        deletes tasks in terminal states (SUCCESS, FAILED, CANCELLED) to
        avoid removing active or pending tasks.

        Args:
            days: Number of days to retain. Tasks older than this are deleted.
            months: Number of months to retain (converted to 30-day periods).
            years: Number of years to retain (converted to 365-day periods).

        Returns:
            int: Number of task records deleted.

        Raises:
            None: Returns 0 if no time period specified.

        Example:
            Cleaning up old tasks::

                # Delete tasks completed over 30 days ago
                deleted = storage.cleanup_old_tasks(days=30)
                print(f"Cleaned up {deleted} old tasks")

                # Delete tasks completed over 3 months ago
                deleted = storage.cleanup_old_tasks(months=3)

                # Delete tasks completed over 1 year ago
                deleted = storage.cleanup_old_tasks(years=1)

                # Combine periods (90 days + 6 months)
                deleted = storage.cleanup_old_tasks(days=90, months=6)

        Note:
            - Only deletes tasks in SUCCESS, FAILED, or CANCELLED status
            - PENDING and STARTED tasks are never deleted
            - Time periods are cumulative if multiple specified
            - Safe to run periodically (e.g., daily cron job)
            - Returns 0 if no time period arguments provided
        """
        if not any([days, months, years]):
            return 0

        self._init_database()
        cutoff_date = datetime.now()
        if days:
            cutoff_date -= timedelta(days=days)
        if months:
            cutoff_date -= timedelta(days=months * 30)
        if years:
            cutoff_date -= timedelta(days=years * 365)

        result = self.connection.execute(
            """
            DELETE FROM tasks 
            WHERE completed_at < ? 
            AND status IN ('success', 'failed', 'cancelled')
        """,
            (cutoff_date.isoformat(),),
        )

        return result.rowcount

    def _row_to_task_info(self, row) -> TaskInfo:
        """Convert a database row tuple to a TaskInfo object.

        Deserializes all fields from database representation back to Python
        objects, including JSON deserialization for complex fields and datetime
        parsing for timestamp fields.

        Args:
            row: Tuple from DuckDB query result containing all task fields
                in the order defined by the table schema.

        Returns:
            TaskInfo object reconstructed from the database row.

        Note:
            - Handles both string and datetime objects for timestamp fields
            - JSON fields (args, kwargs, result) are deserialized from strings
            - Enum fields (priority, status) are converted from stored values
            - Helper function _parse_datetime handles flexible datetime parsing
        """

        def _parse_datetime(dt_value):
            """Parse datetime value that might be string or datetime object.

            Args:
                dt_value: Either a datetime object, ISO string, or None.

            Returns:
                datetime object or None.
            """
            if dt_value is None:
                return None
            if isinstance(dt_value, datetime):
                return dt_value
            return datetime.fromisoformat(dt_value)

        return TaskInfo(
            id=row[0],
            name=row[1],
            category=row[2],
            priority=TaskPriority(row[3]),
            status=TaskStatus(row[4]),
            created_at=_parse_datetime(row[5]),
            started_at=_parse_datetime(row[6]),
            completed_at=_parse_datetime(row[7]),
            elapsed_seconds=row[8] or 0.0,
            result=json.loads(row[9]) if row[9] else None,
            error=row[10],
            retry_count=row[11],
            max_retries=row[12],
            attempt=(row[13] or 0),
            max_attempts=(row[14] or ((row[12] or 0) + 1)),
            idempotency_key=row[15],
            not_before=_parse_datetime(row[16]),
            next_attempt_at=_parse_datetime(row[17]),
            lease_owner=row[18],
            lease_expires_at=_parse_datetime(row[19]),
            claimed_at=_parse_datetime(row[20]),
            last_heartbeat_at=_parse_datetime(row[21]),
            args=tuple(json.loads(row[22])) if row[22] else (),
            kwargs=json.loads(row[23]) if row[23] else {},
            progress=row[24] or 0.0,
            progress_message=row[25] or "",
        )
