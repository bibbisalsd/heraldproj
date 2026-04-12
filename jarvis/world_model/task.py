"""Task and JobStatus dataclasses for task stack management."""

from __future__ import annotations


from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Task:
    """A task in the task stack."""

    task_id: str
    description: str
    priority: int = 0  # Higher = more urgent
    status: str = (
        "pending"  # "pending", "in_progress", "completed", "failed", "cancelled"
    )
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_status(self, status: str) -> "Task":
        """Create a new Task with updated status."""
        valid_statuses = {"pending", "in_progress", "completed", "failed", "cancelled"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid task status: {status}. Must be one of {valid_statuses}"
            )
        return Task(
            task_id=self.task_id,
            description=self.description,
            priority=self.priority,
            status=status,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata=self.metadata,
        )

    def with_priority(self, priority: int) -> "Task":
        """Create a new Task with updated priority."""
        return Task(
            task_id=self.task_id,
            description=self.description,
            priority=priority,
            status=self.status,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class JobStatus:
    """Status of a background job (bg1 lane)."""

    job_id: str
    task_id: str
    status: str = "queued"  # "queued", "running", "completed", "failed", "cancelled"
    progress: float = 0.0  # 0.0 to 1.0
    result: Any = None
    error: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: str | None = None
    completed_at: str | None = None

    def with_status(self, status: str, progress: float | None = None) -> "JobStatus":
        """Create a new JobStatus with updated status."""
        valid_statuses = {"queued", "running", "completed", "failed", "cancelled"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid job status: {status}. Must be one of {valid_statuses}"
            )

        now = datetime.now(timezone.utc).isoformat()
        return JobStatus(
            job_id=self.job_id,
            task_id=self.task_id,
            status=status,
            progress=progress if progress is not None else self.progress,
            result=self.result,
            error=self.error,
            created_at=self.created_at,
            started_at=self.started_at or (now if status == "running" else None),
            completed_at=now
            if status in {"completed", "failed", "cancelled"}
            else self.completed_at,
        )

    def with_result(self, result: Any) -> "JobStatus":
        """Create a new JobStatus with a result."""
        return JobStatus(
            job_id=self.job_id,
            task_id=self.task_id,
            status="completed",
            progress=1.0,
            result=result,
            error=self.error,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    def with_error(self, error: str) -> "JobStatus":
        """Create a new JobStatus with an error."""
        return JobStatus(
            job_id=self.job_id,
            task_id=self.task_id,
            status="failed",
            progress=self.progress,
            result=self.result,
            error=error,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
