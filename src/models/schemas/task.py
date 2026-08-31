"""Task and TaskResult schemas."""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.models.schemas.evidence import Evidence


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    ERROR = "error"


class Task(BaseModel):
    task_id: str
    description: str
    agent_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    output: Any = None
    evidence: list[Evidence] = Field(default_factory=list)
    error: str | None = None
