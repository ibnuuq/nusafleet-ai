"""Tool implementations exposed to agents: read-only SQL execution and
schema introspection against the `fleet` database.

`TOOLS` registers each callable's declarative metadata using the `Tool`
schema from M1 (`src.models.schemas.tool`) -- name/description/
is_read_only, for a future catalog/dispatch layer. Per-call argument and
result validation is a separate, stricter contract per tool (see
`src.tools.schemas`), not expressed by `Tool` itself.
"""
from src.models.schemas.tool import Tool
from src.tools.base import (
    ToolError,
    ToolExecutionError,
    ToolPermissionError,
    ToolTimeoutError,
    ToolValidationError,
)
from src.tools.describe_table import describe_table
from src.tools.execute_sql import execute_sql
from src.tools.get_sample_rows import get_sample_rows
from src.tools.inspect_schema import inspect_schema
from src.tools.schemas import (
    ColumnDetail,
    DescribeTableInput,
    DescribeTableResult,
    ExecuteSqlInput,
    ExecuteSqlResult,
    GetSampleRowsInput,
    GetSampleRowsResult,
    InspectSchemaResult,
    TableSummary,
)

TOOLS: dict[str, Tool] = {
    "execute_sql": Tool(
        name="execute_sql",
        description="Run a read-only SELECT/WITH query against the fleet database.",
        input_schema=ExecuteSqlInput.model_json_schema(),
        is_read_only=True,
    ),
    "inspect_schema": Tool(
        name="inspect_schema",
        description="List tables/views and their columns in the fleet schema.",
        input_schema={},
        is_read_only=True,
    ),
    "describe_table": Tool(
        name="describe_table",
        description="Describe one table's columns, types, and comments.",
        input_schema=DescribeTableInput.model_json_schema(),
        is_read_only=True,
    ),
    "get_sample_rows": Tool(
        name="get_sample_rows",
        description="Return a few example rows from one table.",
        input_schema=GetSampleRowsInput.model_json_schema(),
        is_read_only=True,
    ),
}

__all__ = [
    "TOOLS",
    "ColumnDetail",
    "DescribeTableInput",
    "DescribeTableResult",
    "ExecuteSqlInput",
    "ExecuteSqlResult",
    "GetSampleRowsInput",
    "GetSampleRowsResult",
    "InspectSchemaResult",
    "TableSummary",
    "ToolError",
    "ToolExecutionError",
    "ToolPermissionError",
    "ToolTimeoutError",
    "ToolValidationError",
    "describe_table",
    "execute_sql",
    "get_sample_rows",
    "inspect_schema",
]
