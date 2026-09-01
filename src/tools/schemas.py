"""Pydantic input/output contracts for tools in `src/tools/`.

Distinct from `src.models.schemas.tool.Tool` (M1): that is declarative
tool-catalog metadata -- name/description/is_read_only, registered once
per tool. These models are the per-call argument/result contracts,
validated on every invocation, which `Tool.input_schema` doesn't attempt
to express on its own.
"""
from pydantic import BaseModel, Field


class ExecuteSqlInput(BaseModel):
    query: str = Field(min_length=1)


class ExecuteSqlResult(BaseModel):
    columns: list[str]
    rows: list[dict]
    row_count: int
    execution_ms: float


class TableSummary(BaseModel):
    name: str
    columns: list[str]
    row_estimate: int


class InspectSchemaResult(BaseModel):
    tables: list[TableSummary]


class DescribeTableInput(BaseModel):
    table_name: str = Field(min_length=1)


class ColumnDetail(BaseModel):
    name: str
    type: str
    nullable: bool
    default: str | None
    comment: str | None


class DescribeTableResult(BaseModel):
    table_name: str
    columns: list[ColumnDetail]
    comment: str | None


class GetSampleRowsInput(BaseModel):
    table_name: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=100)


class GetSampleRowsResult(BaseModel):
    columns: list[str]
    rows: list[dict]
    row_count: int
