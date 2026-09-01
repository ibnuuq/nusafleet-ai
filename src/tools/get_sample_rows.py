"""`get_sample_rows` -- a few example rows from one table/view in the
`fleet` schema.

Same allowlist validation as `describe_table`. Unlike `describe_table`'s
`information_schema` lookups, this query must reference the table as a
SQL identifier in `FROM` -- that position can't be parameterized with
`%s` the way a `WHERE` value can. `psycopg2.sql.Identifier` quotes it
instead of string interpolation; the allowlist check happens first, and
the identifier quoting is a second, independent layer on top of it (a
name like `orders; DROP TABLE x` would already fail the allowlist, and
would also come out as a single quoted identifier rather than
executable SQL if it somehow didn't).
"""
from psycopg2 import sql

from src.tools.base import ToolValidationError, _execute, _ro_connection
from src.tools.inspect_schema import fetch_table_allowlist
from src.tools.schemas import GetSampleRowsInput, GetSampleRowsResult


def get_sample_rows(input: GetSampleRowsInput) -> GetSampleRowsResult:
    with _ro_connection() as conn:
        allowlist = fetch_table_allowlist(conn)
        if input.table_name not in allowlist:
            raise ToolValidationError(
                f"unknown table {input.table_name!r}; must be one of the "
                f"fleet schema's real tables/views: {sorted(allowlist)}"
            )

        query = sql.SQL("SELECT * FROM fleet.{table} LIMIT %s").format(
            table=sql.Identifier(input.table_name)
        )
        columns, rows = _execute(conn, query, (input.limit,))
    return GetSampleRowsResult(columns=columns, rows=rows, row_count=len(rows))
