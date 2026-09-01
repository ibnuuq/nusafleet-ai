"""Tests for src/tools/ -- read-only SQL execution and schema introspection
against the real `fleet` database.

Guardrail proofs this file exists to provide (see
docs/architecture/m1_foundation.md, M4 section):
  - read-only is enforced by the `nusafleet_ro` Postgres role, not by our
    query-text validation -- proven by sending writes that *pass* our
    fast prefix check and watching the database reject them anyway;
  - dynamic `table_name` input is checked against a live schema allowlist
    before touching SQL, not string-matched against the request text.

Tests that need a real connection are marked `db` and take the
`require_ro_database` fixture (tests/conftest.py), which skips -- never
fails -- with a clear reason when `DATABASE_URL_RO` is unset or
unreachable, mirroring the live-test skip pattern from M3
(tests/test_llm_live.py).
"""
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.tools import (
    DescribeTableInput,
    ExecuteSqlInput,
    GetSampleRowsInput,
    ToolExecutionError,
    ToolPermissionError,
    ToolTimeoutError,
    ToolValidationError,
    describe_table,
    execute_sql,
    get_sample_rows,
    inspect_schema,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "src" / "tools"


# --- static guardrail: no admin DSN reachable from src/tools/ --------------


def test_tools_never_reference_admin_database_dsn():
    """`src/tools/` must only ever obtain a connection via
    `settings.database_url_ro`. `Settings` doesn't expose an admin/write
    DSN at all (m1_foundation.md, "Why no admin database DSN in
    `Settings`"), so this is structurally impossible today -- this is a
    tripwire against someone adding one later specifically in this
    package. `(?!_ro)` lets `database_url_ro` itself through.
    """
    pattern = re.compile(r"database_url(?!_ro)", re.IGNORECASE)
    offenders = []
    for py_file in TOOLS_DIR.rglob("*.py"):
        for line_no, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line):
                offenders.append((str(py_file.relative_to(REPO_ROOT)), line_no, line.strip()))
    assert not offenders, f"src/tools/ must only use database_url_ro: {offenders}"


# --- settings-only guardrail: missing DATABASE_URL_RO --------------------


def test_execute_sql_without_database_url_ro_raises_execution_error(monkeypatch):
    """No real connection needed for this one -- proves the missing-config
    path in isolation so it still runs even where DATABASE_URL_RO/Postgres
    aren't available at all."""
    from src import config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: config.Settings(_env_file=None, DATABASE_URL_RO=None),
    )
    import src.tools.base as tools_base

    monkeypatch.setattr(tools_base, "get_settings", config.get_settings)

    with pytest.raises(ToolExecutionError, match="DATABASE_URL_RO is not set"):
        execute_sql(ExecuteSqlInput(query="SELECT 1"))


# --- pydantic-level input validation (no DB needed) -----------------------


def test_get_sample_rows_limit_out_of_bounds_rejected_by_pydantic():
    with pytest.raises(ValidationError):
        GetSampleRowsInput(table_name="regions", limit=0)
    with pytest.raises(ValidationError):
        GetSampleRowsInput(table_name="regions", limit=101)


def test_execute_sql_empty_query_rejected_by_pydantic():
    with pytest.raises(ValidationError):
        ExecuteSqlInput(query="")


# --- happy paths against the real database --------------------------------


@pytest.mark.db
def test_inspect_schema_happy_path(require_ro_database):
    result = inspect_schema()
    names = {t.name for t in result.tables}
    assert {"regions", "orders", "deliveries", "vehicles", "drivers"} <= names

    regions = next(t for t in result.tables if t.name == "regions")
    assert "region_code" in regions.columns
    # pg_class.reltuples is a planner estimate, not a live count -- Postgres
    # uses -1 as its own sentinel for "this table has never been ANALYZEd".
    assert regions.row_estimate == -1 or regions.row_estimate >= 0


@pytest.mark.db
def test_describe_table_happy_path(require_ro_database):
    result = describe_table(DescribeTableInput(table_name="deliveries"))
    assert result.table_name == "deliveries"
    col_names = {c.name for c in result.columns}
    assert {"delivery_id", "order_id", "status"} <= col_names

    delivery_id = next(c for c in result.columns if c.name == "delivery_id")
    assert delivery_id.nullable is False
    assert result.comment and "delivery" in result.comment.lower()


@pytest.mark.db
def test_get_sample_rows_happy_path(require_ro_database):
    result = get_sample_rows(GetSampleRowsInput(table_name="regions", limit=3))
    assert result.row_count <= 3
    assert result.row_count == len(result.rows)
    assert "region_code" in result.columns


@pytest.mark.db
def test_execute_sql_happy_path(require_ro_database):
    result = execute_sql(ExecuteSqlInput(query="SELECT region_code FROM regions ORDER BY region_id LIMIT 2"))
    assert result.row_count == 2
    assert result.columns == ["region_code"]
    assert result.execution_ms >= 0


# --- zero rows is not an error ---------------------------------------------


@pytest.mark.db
def test_execute_sql_zero_rows_is_not_an_error(require_ro_database):
    result = execute_sql(ExecuteSqlInput(query="SELECT * FROM regions WHERE region_id = -1"))
    assert result.row_count == 0
    assert result.rows == []
    assert result.columns  # column list still populated even with no rows


# --- dynamic table_name guard: unknown table / injection attempts ---------


@pytest.mark.db
def test_describe_table_unknown_table_raises_validation_error(require_ro_database):
    with pytest.raises(ToolValidationError):
        describe_table(DescribeTableInput(table_name="not_a_real_table"))


@pytest.mark.db
def test_get_sample_rows_unknown_table_raises_validation_error(require_ro_database):
    with pytest.raises(ToolValidationError):
        get_sample_rows(GetSampleRowsInput(table_name="not_a_real_table"))


@pytest.mark.db
def test_get_sample_rows_injection_attempt_rejected_and_data_untouched(require_ro_database):
    """A table_name crafted to look like SQL must be rejected by the
    allowlist check before it ever reaches query construction -- it never
    gets a chance to be quoted, let alone executed."""
    before = execute_sql(ExecuteSqlInput(query="SELECT count(*) AS n FROM regions"))

    with pytest.raises(ToolValidationError):
        get_sample_rows(GetSampleRowsInput(table_name='regions"; DROP TABLE regions; --'))

    after = execute_sql(ExecuteSqlInput(query="SELECT count(*) AS n FROM regions"))
    assert before.rows == after.rows


# --- read-only guardrail: the database rejects writes, not our string check ---


@pytest.mark.db
def test_execute_sql_plain_write_rejected_by_fast_prefix_check(require_ro_database):
    """This one never reaches the database at all -- it's the fast
    pre-check saving a round trip. Proof that the *database* is the real
    guard is the next two tests, which deliberately get past this check.
    """
    with pytest.raises(ToolValidationError):
        execute_sql(ExecuteSqlInput(query="UPDATE regions SET region_name = region_name"))


@pytest.mark.db
def test_execute_sql_write_disguised_as_select_rejected_by_database(require_ro_database):
    """Passes the fast prefix check (starts with WITH) but performs a
    DELETE inside a CTE -- rejected by Postgres itself
    (ReadOnlySqlTransaction on the nusafleet_ro role), proving the
    database is the actual enforcement point."""
    with pytest.raises(ToolPermissionError):
        execute_sql(
            ExecuteSqlInput(query="WITH x AS (DELETE FROM regions RETURNING *) SELECT * FROM x")
        )

    result = execute_sql(ExecuteSqlInput(query="SELECT count(*) AS n FROM regions"))
    assert result.rows[0]["n"] > 0


@pytest.mark.db
def test_execute_sql_multi_statement_drop_rejected_by_database(require_ro_database):
    """Passes the fast prefix check (starts with SELECT) but appends a
    second statement that drops the table -- also rejected by Postgres,
    and the table survives."""
    with pytest.raises(ToolPermissionError):
        execute_sql(ExecuteSqlInput(query="SELECT 1; DROP TABLE regions;"))

    result = execute_sql(ExecuteSqlInput(query="SELECT count(*) AS n FROM regions"))
    assert result.rows[0]["n"] > 0


@pytest.mark.db
def test_execute_sql_cannot_reach_outside_fleet_schema(require_ro_database):
    """`information_schema`/`pg_catalog` are reachable (used by
    inspect_schema/describe_table), but another schema's tables are not --
    the role was simply never granted SELECT on them."""
    with pytest.raises(ToolPermissionError):
        execute_sql(ExecuteSqlInput(query="SELECT * FROM pg_authid"))


# --- timeout and large result set ------------------------------------------


@pytest.mark.db
@pytest.mark.slow
def test_execute_sql_timeout_raises_tool_timeout_error(require_ro_database):
    """Exercises the real `statement_timeout = 30s` set on `nusafleet_ro`
    in schema.sql -- deliberately slow (~30s)."""
    with pytest.raises(ToolTimeoutError):
        execute_sql(ExecuteSqlInput(query="SELECT pg_sleep(35)"))


@pytest.mark.db
def test_execute_sql_large_result_set(require_ro_database):
    result = execute_sql(ExecuteSqlInput(query="SELECT generate_series(1, 50000) AS n"))
    assert result.row_count == 50000
    assert len(result.rows) == 50000
