"""`describe_table` -- column detail for one table/view in the `fleet`
schema.

`table_name` is validated against the live allowlist from
`inspect_schema.fetch_table_allowlist` *before* it is used in any query --
resolve-then-check, the same shape as the `artifact_dir` validator in
`src/config.py`, not a substring check against the request text. Every
query below binds `table_name` as a parameter (`%s`), never interpolates
it into SQL text, even though it has already passed the allowlist --
defense in depth, same rationale as elsewhere in this project.
"""
from src.tools.base import ToolValidationError, _execute, _ro_connection
from src.tools.inspect_schema import fetch_table_allowlist
from src.tools.schemas import ColumnDetail, DescribeTableInput, DescribeTableResult

_COLUMNS_QUERY = """
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_schema = 'fleet' AND table_name = %s
    ORDER BY ordinal_position
"""

_TABLE_COMMENT_QUERY = """
    SELECT obj_description(c.oid) AS comment
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'fleet' AND c.relname = %s
"""

_COLUMN_COMMENTS_QUERY = """
    SELECT a.attname AS column_name, col_description(c.oid, a.attnum) AS comment
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
    WHERE n.nspname = 'fleet' AND c.relname = %s
"""


def describe_table(input: DescribeTableInput) -> DescribeTableResult:
    with _ro_connection() as conn:
        allowlist = fetch_table_allowlist(conn)
        if input.table_name not in allowlist:
            raise ToolValidationError(
                f"unknown table {input.table_name!r}; must be one of the "
                f"fleet schema's real tables/views: {sorted(allowlist)}"
            )

        _, column_rows = _execute(conn, _COLUMNS_QUERY, (input.table_name,))
        _, comment_rows = _execute(conn, _TABLE_COMMENT_QUERY, (input.table_name,))
        _, col_comment_rows = _execute(conn, _COLUMN_COMMENTS_QUERY, (input.table_name,))

    col_comments = {r["column_name"]: r["comment"] for r in col_comment_rows}
    table_comment = comment_rows[0]["comment"] if comment_rows else None

    columns = [
        ColumnDetail(
            name=r["column_name"],
            type=r["data_type"],
            nullable=(r["is_nullable"] == "YES"),
            default=r["column_default"],
            comment=col_comments.get(r["column_name"]),
        )
        for r in column_rows
    ]
    return DescribeTableResult(table_name=input.table_name, columns=columns, comment=table_comment)
