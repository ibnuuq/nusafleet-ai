"""`inspect_schema` -- list tables/views and columns in the `fleet` schema.

`fetch_table_allowlist` is also the source of truth for the runtime
table-name allowlist used by `describe_table` and `get_sample_rows`: it
queries the live schema for real table/view names, so the allowlist can
never drift from what actually exists and is never derived from request
text (docs/architecture/m1_foundation.md, "Known limitation: isolation is
static, not yet a runtime guard" -- resolve the concrete target, then
check an explicit allowlist).
"""
from src.tools.base import _execute, _ro_connection
from src.tools.schemas import InspectSchemaResult, TableSummary

_TABLES_QUERY = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'fleet'
    ORDER BY table_name
"""

_COLUMNS_QUERY = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = 'fleet' AND table_name = %s
    ORDER BY ordinal_position
"""

_ROW_ESTIMATE_QUERY = """
    SELECT reltuples::bigint AS row_estimate
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'fleet' AND c.relname = %s
"""


def fetch_table_allowlist(conn) -> list[str]:
    """Query the live `fleet` schema for real table/view names. This *is*
    the allowlist -- never a hardcoded list, never the request text."""
    _, rows = _execute(conn, _TABLES_QUERY)
    return [r["table_name"] for r in rows]


def inspect_schema() -> InspectSchemaResult:
    with _ro_connection() as conn:
        table_names = fetch_table_allowlist(conn)
        tables = []
        for name in table_names:
            _, column_rows = _execute(conn, _COLUMNS_QUERY, (name,))
            _, estimate_rows = _execute(conn, _ROW_ESTIMATE_QUERY, (name,))
            row_estimate = (
                int(estimate_rows[0]["row_estimate"])
                if estimate_rows and estimate_rows[0]["row_estimate"] is not None
                else 0
            )
            tables.append(
                TableSummary(
                    name=name,
                    columns=[r["column_name"] for r in column_rows],
                    row_estimate=row_estimate,
                )
            )
    return InspectSchemaResult(tables=tables)
