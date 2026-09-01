"""Shared plumbing for tools: exception hierarchy, the one and only
database connection path (`settings.database_url_ro`), and psycopg2 error
mapping.

The exception hierarchy mirrors `src.models.llm.base.LLMError` from M3 so
future orchestrator code can `except ToolError` uniformly across LLM and
tool failures.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.errors
import psycopg2.extras
from psycopg2 import sql

from src.config import get_settings


class ToolError(RuntimeError):
    """Base of the tool exception hierarchy."""


class ToolValidationError(ToolError):
    """Input failed validation before any query was sent to the database
    (e.g. an unknown table name, a non-SELECT query). Distinct from
    `ToolPermissionError`: this is *our* check, not the database's."""


class ToolPermissionError(ToolError):
    """The database rejected the operation -- not a check performed in
    this code. Raised when the `nusafleet_ro` role's read-only-transaction
    guard or a privilege grant is what actually said no."""


class ToolTimeoutError(ToolError):
    """The query exceeded the role's `statement_timeout` (30s, set on
    `nusafleet_ro` in schema.sql)."""


class ToolExecutionError(ToolError):
    """Any other database error: connection failure, malformed SQL, an
    unexpected server-side error."""


@contextmanager
def _ro_connection() -> Iterator[psycopg2.extensions.connection]:
    """The only place `src/tools/` opens a database connection. Always
    `settings.database_url_ro` -- there is no admin/write DSN reachable
    from this package, by construction (`Settings` doesn't expose one; see
    docs/architecture/m1_foundation.md, "Why no admin database DSN in
    `Settings`"). A missing `DATABASE_URL_RO` or a connection failure
    raises `ToolExecutionError`, so callers only ever need to catch
    `ToolError`.
    """
    settings = get_settings()
    if not settings.database_url_ro:
        raise ToolExecutionError(
            "DATABASE_URL_RO is not set -- tools require a read-only "
            "database connection string (see docs/architecture/m1_foundation.md)"
        )
    try:
        conn = psycopg2.connect(settings.database_url_ro.get_secret_value(), connect_timeout=10)
    except psycopg2.OperationalError as exc:
        raise ToolExecutionError(f"could not connect to database: {exc}") from exc
    try:
        yield conn
    finally:
        conn.close()


def _execute(
    conn: psycopg2.extensions.connection,
    query: str | sql.Composable,
    params: tuple = (),
) -> tuple[list[str], list[dict[str, Any]]]:
    """Run one statement over `conn` and map psycopg2 errors onto the tool
    exception hierarchy.

    This is the single place a write attempt actually gets rejected -- by
    the database saying no (`ReadOnlySqlTransaction` /
    `InsufficientPrivilege`), not by us recognizing the query text. A
    query wrapped to disguise a write (e.g. a CTE ending in a bare
    `SELECT` but performing a `DELETE` inside) is still caught here,
    empirically verified against the running `nusafleet_ro` role.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        try:
            cur.execute(query, params)
        except psycopg2.errors.QueryCanceled as exc:
            raise ToolTimeoutError(f"query exceeded statement_timeout: {exc}") from exc
        except (psycopg2.errors.ReadOnlySqlTransaction, psycopg2.errors.InsufficientPrivilege) as exc:
            raise ToolPermissionError(f"database rejected the operation: {exc}") from exc
        except psycopg2.Error as exc:
            raise ToolExecutionError(f"query failed: {exc}") from exc

        if cur.description is None:
            return [], []
        columns = [d.name for d in cur.description]
        rows = [dict(r) for r in cur.fetchall()]
        return columns, rows


def _timed_query(query: str | sql.Composable, params: tuple = ()) -> tuple[list[str], list[dict], float]:
    """Open a fresh read-only connection, run one statement, and return
    `(columns, rows, execution_ms)`. Used by `execute_sql`, where timing
    exactly one statement is the point."""
    start = time.perf_counter()
    with _ro_connection() as conn:
        columns, rows = _execute(conn, query, params)
    return columns, rows, (time.perf_counter() - start) * 1000
