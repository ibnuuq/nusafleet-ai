"""RunState schema -- the top-level state of one investigation run."""
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from src.models.schemas.task import Task, TaskResult


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class RunState(BaseModel):
    run_id: str
    question: str
    status: RunStatus = RunStatus.PENDING
    tasks: list[Task] = Field(default_factory=list)
    results: list[TaskResult] = Field(default_factory=list)
    iteration: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
