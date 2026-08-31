"""Tool schema -- describes a callable capability exposed to agents.

`is_read_only` is a declarative guardrail flag. It documents intent; it does
not by itself enforce anything -- actual write protection belongs at the
execution layer (e.g. the Postgres `nusafleet_ro` role), per
design_dataset_and_scenarios.md section 9 (F10).
"""
from typing import Any

from pydantic import BaseModel, Field


class Tool(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    is_read_only: bool = True
