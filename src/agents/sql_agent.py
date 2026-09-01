"""SQL Agent -- the first agent that connects an `LLMProvider` (M3) to the
read-only tools (M4). One agent, no planner, no orchestrator: it takes a
natural-language question and returns a structured answer backed by the
SQL it ran.

Both `llm` and `tools` are constructor/call-time dependencies, never
hardcoded, so this module can be exercised with any `LLMProvider`
implementation and with fake tools in tests -- see
`docs/architecture/m1_foundation.md`, "M5 — SQL Agent" for the guardrail
rationale (F01 self-debug loop, F11 context blow-up mitigation).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable
from uuid import uuid4

from pydantic import BaseModel

from src.models.llm.base import LLMProvider
from src.models.schemas.evidence import Evidence, EvidenceKind
from src.tools import (
    DescribeTableInput,
    DescribeTableResult,
    ExecuteSqlInput,
    ExecuteSqlResult,
    InspectSchemaResult,
    ToolError,
    describe_table,
    execute_sql,
    inspect_schema,
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_ROWS_FOR_LLM = 50
DEFAULT_MAX_CHARS_FOR_LLM = 12_000


@dataclass
class SQLAgentTools:
    """The subset of `src/tools/` this agent actually uses. Defaults to
    the real M4 functions, which each open their own connection via
    `settings.database_url_ro` -- the agent never touches the database
    directly, only through these. Swappable in tests for deterministic,
    offline coverage of the loop/truncation logic."""

    execute_sql: Callable[[ExecuteSqlInput], ExecuteSqlResult] = execute_sql
    inspect_schema: Callable[[], InspectSchemaResult] = inspect_schema
    describe_table: Callable[[DescribeTableInput], DescribeTableResult] = describe_table


DEFAULT_TOOLS = SQLAgentTools()


class SQLAgentAnswer(BaseModel):
    question: str
    answer: str
    sql: str | None
    success: bool
    row_count: int | None
    rows_sent_to_llm: int | None
    truncated: bool
    attempts: int
    provider: str
    model: str
    evidence: list[Evidence]
    error: str | None


_SQL_SYSTEM_PROMPT = (
    "Anda adalah SQL Agent untuk database armada logistik `fleet` (Postgres). "
    "Tulis SATU query SQL read-only (SELECT atau WITH ... SELECT) yang menjawab "
    "pertanyaan pengguna berdasarkan skema yang diberikan. Balas HANYA dengan satu "
    "blok kode berpagar ```sql ... ```, tanpa penjelasan apa pun di luar blok kode. "
    "Jangan pernah menulis INSERT/UPDATE/DELETE/DROP/ALTER -- koneksi hanya "
    "berizin read-only dan akan menolaknya."
)

_SUMMARY_SYSTEM_PROMPT = (
    "Anda adalah asisten analitik untuk data armada logistik. Jawab pertanyaan "
    "pengguna HANYA berdasarkan hasil query SQL yang diberikan di bawah -- jangan "
    "mengarang angka atau fakta yang tidak ada di data. Kalau hasil query kosong "
    "(0 baris), katakan dengan jelas bahwa tidak ada data yang cocok dan usulkan "
    "pelonggaran filter. Kalau data yang ditampilkan hanya sebagian dari hasil "
    "penuh (dipotong), sebutkan itu secara eksplisit ke pengguna dan jangan "
    "menyimpulkan seolah-olah itu keseluruhan data."
)

_SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def _extract_sql(text: str) -> str:
    match = _SQL_FENCE_RE.search(text)
    candidate = match.group(1) if match else text
    return candidate.strip().rstrip(";").strip()


def _tables_referenced(sql: str, known_tables: set[str]) -> list[str]:
    found = {m.group(1) for m in _TABLE_REF_RE.finditer(sql)}
    return sorted(t for t in found if t in known_tables)[:2]


def _build_schema_summary(schema: InspectSchemaResult) -> str:
    lines = ["Tabel yang tersedia di skema `fleet`:"]
    for t in schema.tables:
        lines.append(f"- {t.name}({', '.join(t.columns)})")
    return "\n".join(lines)


def _format_table_detail(detail: DescribeTableResult) -> str:
    header = f"Detail tabel `{detail.table_name}`"
    if detail.comment:
        header += f" -- {detail.comment}"
    lines = [header + ":"]
    for c in detail.columns:
        nullable = "NULL" if c.nullable else "NOT NULL"
        comment = f" -- {c.comment}" if c.comment else ""
        lines.append(f"  - {c.name} {c.type} {nullable}{comment}")
    return "\n".join(lines)


def _build_sql_prompt(question: str, schema_summary: str, history: list[dict]) -> str:
    parts = [schema_summary, "", f"Pertanyaan: {question}"]
    if history:
        parts.append("")
        parts.append("Percobaan sebelumnya gagal. Perbaiki query berdasarkan error berikut:")
        for i, attempt in enumerate(history, start=1):
            parts.append(f"\nPercobaan {i}:")
            parts.append(f"SQL:\n{attempt['sql']}")
            parts.append(f"Error: {attempt['error']}")
            for detail in attempt.get("details", []):
                parts.append(detail)
        parts.append("\nTulis ulang query yang memperbaiki error di atas.")
    return "\n".join(parts)


def _prepare_rows_for_llm(
    rows: list[dict], max_rows: int, max_chars: int
) -> tuple[list[dict], bool]:
    """F11 mitigation: cap what reaches the LLM by row count AND a
    character budget (a handful of wide rows can blow the budget before
    `max_rows` is reached). Never called with the raw, unbounded result --
    this is the one place a query result is allowed to reach a prompt."""
    selected: list[dict] = []
    total_chars = 0
    for i, row in enumerate(rows):
        if i >= max_rows:
            break
        row_str = json.dumps(row, default=str, ensure_ascii=False)
        if selected and total_chars + len(row_str) > max_chars:
            break
        selected.append(row)
        total_chars += len(row_str)
    truncated = len(selected) < len(rows)
    return selected, truncated


def _build_summary_prompt(
    question: str,
    sql: str,
    result: ExecuteSqlResult,
    rows_for_llm: list[dict],
    truncated: bool,
) -> str:
    parts = [
        f"Pertanyaan: {question}",
        f"\nSQL yang dijalankan:\n{sql}",
        f"\nJumlah baris hasil: {result.row_count}",
        f"Kolom: {', '.join(result.columns)}",
    ]
    if result.row_count == 0:
        parts.append("\n[Hasil query KOSONG -- 0 baris. Tidak ada data yang cocok dengan kriteria.]")
    else:
        if truncated:
            parts.append(
                f"\n[PERINGATAN: hasil dipotong untuk menghindari context blow-up. Total "
                f"{result.row_count} baris, hanya {len(rows_for_llm)} baris pertama "
                "ditampilkan di bawah. JANGAN menyimpulkan ini sebagai keseluruhan data -- "
                "sebutkan eksplisit ke pengguna bahwa ini contoh sebagian, bukan data penuh.]"
            )
        parts.append(f"\nData ({len(rows_for_llm)} dari {result.row_count} baris):")
        parts.append(json.dumps(rows_for_llm, default=str, ensure_ascii=False, indent=2))
    parts.append("\nBerikan jawaban ringkas dan akurat dalam Bahasa Indonesia berdasarkan data di atas.")
    return "\n".join(parts)


async def answer_question(
    question: str,
    *,
    llm: LLMProvider,
    tools: SQLAgentTools = DEFAULT_TOOLS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_rows_for_llm: int = DEFAULT_MAX_ROWS_FOR_LLM,
    max_chars_for_llm: int = DEFAULT_MAX_CHARS_FOR_LLM,
) -> SQLAgentAnswer:
    """Answer `question` by writing SQL, running it via `tools.execute_sql`,
    and summarizing the (bounded) result with `llm`.

    F01: up to `max_attempts` SQL write/execute cycles; a failure feeds the
    error (and, when a referenced table is identifiable, its
    `describe_table` detail) back to the LLM for the next attempt. After
    `max_attempts` the loop stops and reports failure honestly -- no
    summarization call is made, so there is nothing for the LLM to invent
    an answer from.

    F11: only `execute_sql`'s connection is unbounded (by M4 design); the
    result is truncated by `_prepare_rows_for_llm` before it ever reaches
    a prompt, and `truncated`/`row_count`/`rows_sent_to_llm` on the
    returned `SQLAgentAnswer` make that visible structurally, not just in
    the LLM's prose.

    Raises `LLMError` if the provider itself fails (timeout, rate limit,
    etc.) -- that is a different failure mode from a bad SQL query and is
    not retried by this loop.
    """
    schema = tools.inspect_schema()
    known_tables = {t.name for t in schema.tables}
    schema_summary = _build_schema_summary(schema)

    history: list[dict] = []
    last_response = None
    last_sql: str | None = None
    last_error: str | None = None
    result: ExecuteSqlResult | None = None
    attempt = 0

    for attempt in range(1, max_attempts + 1):
        prompt = _build_sql_prompt(question, schema_summary, history)
        last_response = await llm.generate(prompt, system=_SQL_SYSTEM_PROMPT, temperature=0.0)
        sql = _extract_sql(last_response.text)
        last_sql = sql

        try:
            result = tools.execute_sql(ExecuteSqlInput(query=sql))
            break
        except ToolError as exc:
            last_error = str(exc)
            details = [
                _format_table_detail(tools.describe_table(DescribeTableInput(table_name=t)))
                for t in _tables_referenced(sql, known_tables)
            ]
            history.append({"sql": sql, "error": last_error, "details": details})
            result = None

    provider = last_response.provider if last_response else "unknown"
    model = last_response.model if last_response else "unknown"

    if result is None:
        return SQLAgentAnswer(
            question=question,
            answer=(
                f"Gagal menjalankan query setelah {max_attempts} percobaan. "
                f"Error terakhir: {last_error}"
            ),
            sql=last_sql,
            success=False,
            row_count=None,
            rows_sent_to_llm=None,
            truncated=False,
            attempts=attempt,
            provider=provider,
            model=model,
            evidence=[
                Evidence(
                    evidence_id=str(uuid4()),
                    kind=EvidenceKind.SQL_QUERY,
                    content=last_sql,
                    source="sql_agent:failed",
                )
            ],
            error=last_error,
        )

    rows_for_llm, truncated = _prepare_rows_for_llm(result.rows, max_rows_for_llm, max_chars_for_llm)
    summary_prompt = _build_summary_prompt(question, last_sql, result, rows_for_llm, truncated)
    summary_response = await llm.generate(summary_prompt, system=_SUMMARY_SYSTEM_PROMPT, temperature=0.2)

    evidence = [
        Evidence(
            evidence_id=str(uuid4()),
            kind=EvidenceKind.SQL_QUERY,
            content=last_sql,
            source="sql_agent",
        ),
        Evidence(
            evidence_id=str(uuid4()),
            kind=EvidenceKind.TABLE,
            content={
                "columns": result.columns,
                "rows": rows_for_llm,
                "total_row_count": result.row_count,
                "truncated": truncated,
            },
            source="execute_sql",
        ),
    ]

    return SQLAgentAnswer(
        question=question,
        answer=summary_response.text,
        sql=last_sql,
        success=True,
        row_count=result.row_count,
        rows_sent_to_llm=len(rows_for_llm),
        truncated=truncated,
        attempts=attempt,
        provider=summary_response.provider,
        model=summary_response.model,
        evidence=evidence,
        error=None,
    )
