"""`execute_sql` -- run a read-only query against the `fleet` schema.

Read-only is enforced by the database connection -- the `nusafleet_ro`
Postgres role (`default_transaction_read_only = on`,
`search_path = fleet, public`, `statement_timeout = 30s`; see
schema.sql) -- not by validating the query text. The prefix check below
is a fast pre-check only: it saves a round trip for an obvious
non-SELECT, it is not the security boundary. A write disguised to pass
the prefix check (e.g. `WITH x AS (DELETE FROM t RETURNING *) SELECT *
FROM x`) still starts with `WITH` and is let through here, and is then
rejected by Postgres itself with `ReadOnlySqlTransaction` -- empirically
verified against the running `nusafleet_ro` role -- surfacing as
`ToolPermissionError`, not `ToolValidationError`.

`information_schema`/`pg_catalog` are reachable through this connection
for introspection (they back `inspect_schema`/`describe_table`) -- a
deliberate, documented choice, not an oversight. Access to schemas/tables
outside `fleet` is blocked by the role's grants (it was never granted
`SELECT` on anything else), not by `search_path`; `search_path` only
affects unqualified names, so an explicitly schema-qualified query (e.g.
`SELECT * FROM pg_authid`) is stopped by `InsufficientPrivilege`, also
empirically verified.
"""
import re

from src.tools.base import ToolValidationError, _timed_query
from src.tools.schemas import ExecuteSqlInput, ExecuteSqlResult

_READ_ONLY_PREFIX = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


def execute_sql(input: ExecuteSqlInput) -> ExecuteSqlResult:
    if not _READ_ONLY_PREFIX.match(input.query):
        raise ToolValidationError(
            "execute_sql only accepts queries starting with SELECT/WITH; "
            "the database connection enforces read-only regardless of this "
            "check, but this fails fast without a round trip"
        )
    columns, rows, execution_ms = _timed_query(input.query)
    return ExecuteSqlResult(
        columns=columns, rows=rows, row_count=len(rows), execution_ms=execution_ms
    )
