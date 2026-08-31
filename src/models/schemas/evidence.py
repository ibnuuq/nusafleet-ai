"""Evidence schema -- an artifact backing a claim made by an agent."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvidenceKind(str, Enum):
    SQL_QUERY = "sql_query"
    TABLE = "table"
    CHART = "chart"
    TEXT = "text"


class Evidence(BaseModel):
    evidence_id: str
    kind: EvidenceKind
    content: Any
    source: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
