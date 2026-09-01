"""Tests for src/agents/sql_agent.py.

Deterministic tests use `FakeLLMProvider` + fake `SQLAgentTools` -- no
live LLM or database needed, and no dependence on an LLM's prose being
reproducible. These are what actually prove the F01 (self-debug loop) and
F11 (context blow-up) guardrails: outcomes are asserted on structured
fields (`success`, `attempts`, `truncated`, `row_count`, captured prompt
text), not by parsing what the LLM said.

Live tests (`@pytest.mark.live`, `@pytest.mark.db`) exercise the real
pipeline end-to-end against OpenRouter/Ollama and the real `fleet`
database, with self-authored questions -- eval/reference/ is ground truth
and was not read to write these; the questions here are original.
"""
import pytest

from src.agents.sql_agent import (
    DEFAULT_MAX_ROWS_FOR_LLM,
    SQLAgentTools,
    _prepare_rows_for_llm,
    answer_question,
)
from src.config import get_settings
from src.models.llm.base import LLMError, LLMProvider, LLMResponse
from src.models.llm.gemini import GeminiProvider
from src.models.llm.ollama import OllamaProvider
from src.models.schemas.evidence import EvidenceKind
from src.tools import (
    ColumnDetail,
    DescribeTableResult,
    ExecuteSqlResult,
    InspectSchemaResult,
    TableSummary,
    ToolExecutionError,
)


class FakeLLMProvider(LLMProvider):
    """Deterministic stand-in for a real provider: returns canned
    responses in order and records every prompt/system it was given, so
    tests can assert on exactly what the agent sent."""

    name = "fake"

    def __init__(self, responses: list[str], model: str = "fake-model"):
        self._responses = list(responses)
        self._model = model
        self.prompts: list[str] = []
        self.systems: list[str | None] = []

    async def generate(self, prompt, *, system=None, temperature=0.2, max_tokens=None):
        self.prompts.append(prompt)
        self.systems.append(system)
        if not self._responses:
            raise LLMError("FakeLLMProvider ran out of canned responses")
        return LLMResponse(text=self._responses.pop(0), provider=self.name, model=self._model)

    async def health_check(self):
        return True


def _fail_describe_table(_input):
    pytest.fail("describe_table should not be called on this path")


# --- happy path --------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_question_happy_path_no_truncation():
    schema = InspectSchemaResult(
        tables=[TableSummary(name="regions", columns=["region_id", "region_code"], row_estimate=9)]
    )
    result = ExecuteSqlResult(
        columns=["region_code"],
        rows=[{"region_code": "JKT"}, {"region_code": "MKS"}],
        row_count=2,
        execution_ms=1.2,
    )
    llm = FakeLLMProvider(["```sql\nSELECT region_code FROM regions```", "Ada 2 region: JKT dan MKS."])
    tools = SQLAgentTools(
        execute_sql=lambda inp: result,
        inspect_schema=lambda: schema,
        describe_table=_fail_describe_table,
    )

    answer = await answer_question("Sebutkan semua kode region", llm=llm, tools=tools)

    assert answer.success is True
    assert answer.attempts == 1
    assert answer.row_count == 2
    assert answer.rows_sent_to_llm == 2
    assert answer.truncated is False
    assert answer.sql == "SELECT region_code FROM regions"
    assert answer.answer == "Ada 2 region: JKT dan MKS."
    assert answer.provider == "fake"
    assert answer.error is None
    assert len(answer.evidence) == 2
    assert answer.evidence[0].kind == EvidenceKind.SQL_QUERY
    assert answer.evidence[0].content == "SELECT region_code FROM regions"
    assert answer.evidence[1].kind == EvidenceKind.TABLE
    assert answer.evidence[1].content["total_row_count"] == 2
    assert answer.evidence[1].content["truncated"] is False


@pytest.mark.asyncio
async def test_answer_question_zero_rows_is_not_an_error():
    """F02: 0 rows is a successful, well-formed answer, not an error --
    and the summarization prompt tells the LLM explicitly so it doesn't
    invent data."""
    schema = InspectSchemaResult(tables=[TableSummary(name="regions", columns=["region_id"], row_estimate=9)])
    result = ExecuteSqlResult(columns=["region_id"], rows=[], row_count=0, execution_ms=0.5)
    llm = FakeLLMProvider(
        ["```sql\nSELECT region_id FROM regions WHERE region_id = 9999```", "Tidak ada data yang cocok."]
    )
    tools = SQLAgentTools(
        execute_sql=lambda inp: result,
        inspect_schema=lambda: schema,
        describe_table=_fail_describe_table,
    )

    answer = await answer_question("Ada region dengan id 9999?", llm=llm, tools=tools)

    assert answer.success is True
    assert answer.row_count == 0
    assert answer.rows_sent_to_llm == 0
    assert answer.truncated is False
    assert "KOSONG" in llm.prompts[-1]


# --- F01: self-debug loop -----------------------------------------------------


@pytest.mark.asyncio
async def test_answer_question_self_debug_loop_stops_at_max_attempts():
    schema = InspectSchemaResult(
        tables=[TableSummary(name="regions", columns=["region_id", "region_code"], row_estimate=9)]
    )

    def always_fails(_input):
        raise ToolExecutionError('column "not_a_real_column" does not exist')

    detail_calls: list[str] = []

    def fake_describe_table(input):
        detail_calls.append(input.table_name)
        return DescribeTableResult(
            table_name="regions",
            columns=[ColumnDetail(name="region_id", type="smallint", nullable=False, default=None, comment=None)],
            comment=None,
        )

    llm = FakeLLMProvider(["```sql\nSELECT not_a_real_column FROM regions```"] * 3)
    tools = SQLAgentTools(execute_sql=always_fails, inspect_schema=lambda: schema, describe_table=fake_describe_table)

    answer = await answer_question("Ambil kolom yang tidak ada", llm=llm, tools=tools, max_attempts=3)

    assert answer.success is False
    assert answer.attempts == 3
    assert "3 percobaan" in answer.answer
    assert answer.error is not None and "not_a_real_column" in answer.error
    assert answer.row_count is None
    assert answer.sql == "SELECT not_a_real_column FROM regions"
    # exactly 3 SQL-writing calls, and never a 4th (summarization) call --
    # nothing for the LLM to hallucinate an answer from.
    assert len(llm.prompts) == 3
    assert detail_calls == ["regions", "regions", "regions"]
    assert len(answer.evidence) == 1
    assert answer.evidence[0].kind == EvidenceKind.SQL_QUERY


@pytest.mark.asyncio
async def test_answer_question_self_debug_loop_recovers_on_retry():
    """A more realistic case than always-fails: attempt 1 has a typo'd
    column, the agent re-inspects the table, and the corrected query on
    attempt 2 succeeds -- proving the loop can recover, not just exhaust.
    """
    schema = InspectSchemaResult(
        tables=[TableSummary(name="regions", columns=["region_id", "region_code"], row_estimate=9)]
    )
    calls = {"n": 0}

    def execute_sql_impl(input):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ToolExecutionError('column "region_cod" does not exist')
        return ExecuteSqlResult(columns=["region_code"], rows=[{"region_code": "JKT"}], row_count=1, execution_ms=0.4)

    def fake_describe_table(input):
        return DescribeTableResult(
            table_name="regions",
            columns=[ColumnDetail(name="region_code", type="text", nullable=False, default=None, comment=None)],
            comment=None,
        )

    llm = FakeLLMProvider(
        [
            "```sql\nSELECT region_cod FROM regions```",
            "```sql\nSELECT region_code FROM regions```",
            "Region-nya JKT.",
        ]
    )
    tools = SQLAgentTools(execute_sql=execute_sql_impl, inspect_schema=lambda: schema, describe_table=fake_describe_table)

    answer = await answer_question("Region apa saja?", llm=llm, tools=tools)

    assert answer.success is True
    assert answer.attempts == 2
    assert answer.sql == "SELECT region_code FROM regions"
    assert "Percobaan sebelumnya gagal" in llm.prompts[1]
    assert "region_code" in llm.prompts[1]  # describe_table detail made it into the repair prompt


# --- F11: context blow-up mitigation ------------------------------------------


def test_prepare_rows_for_llm_respects_row_cap():
    rows = [{"n": i} for i in range(50_000)]
    selected, truncated = _prepare_rows_for_llm(rows, max_rows=50, max_chars=1_000_000)
    assert len(selected) == 50
    assert truncated is True


def test_prepare_rows_for_llm_respects_char_budget_even_under_row_cap():
    wide_rows = [{"blob": "x" * 5_000} for _ in range(10)]
    selected, truncated = _prepare_rows_for_llm(wide_rows, max_rows=50, max_chars=12_000)
    assert truncated is True
    assert len(selected) < 10


def test_prepare_rows_for_llm_no_truncation_when_result_fits():
    rows = [{"n": i} for i in range(5)]
    selected, truncated = _prepare_rows_for_llm(rows, max_rows=50, max_chars=12_000)
    assert selected == rows
    assert truncated is False


@pytest.mark.asyncio
async def test_answer_question_truncates_large_result_for_llm():
    schema = InspectSchemaResult(
        tables=[TableSummary(name="deliveries", columns=["delivery_id", "status"], row_estimate=200_000)]
    )
    big_rows = [{"delivery_id": i, "status": "delivered"} for i in range(50_000)]
    result = ExecuteSqlResult(columns=["delivery_id", "status"], rows=big_rows, row_count=50_000, execution_ms=120.0)
    llm = FakeLLMProvider(
        ["```sql\nSELECT delivery_id, status FROM deliveries```", "Ringkasan: 50.000 baris ditemukan (dipotong)."]
    )
    tools = SQLAgentTools(
        execute_sql=lambda inp: result,
        inspect_schema=lambda: schema,
        describe_table=_fail_describe_table,
    )

    answer = await answer_question("Tampilkan semua delivery", llm=llm, tools=tools)

    assert answer.success is True
    assert answer.row_count == 50_000
    assert answer.rows_sent_to_llm == DEFAULT_MAX_ROWS_FOR_LLM
    assert answer.truncated is True

    summary_prompt = llm.prompts[-1]
    assert "PERINGATAN" in summary_prompt
    # context did not blow up: the prompt is small, not proportional to 50,000 rows
    assert len(summary_prompt) < 20_000

    table_evidence = answer.evidence[1]
    assert table_evidence.content["truncated"] is True
    assert table_evidence.content["total_row_count"] == 50_000
    assert len(table_evidence.content["rows"]) == DEFAULT_MAX_ROWS_FOR_LLM


# --- live end-to-end -----------------------------------------------------------


@pytest.fixture
def require_openrouter() -> GeminiProvider:
    settings = get_settings()
    if not settings.openrouter_api_key:
        pytest.skip("OPENROUTER_API_KEY not set in environment/.env -- skipping live SQL Agent test")
    return GeminiProvider(api_key=settings.openrouter_api_key.get_secret_value(), model=settings.gemini_model)


@pytest.fixture
async def require_ollama() -> OllamaProvider:
    settings = get_settings()
    provider = OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    if not await provider.health_check():
        pytest.skip(f"Ollama not reachable at {settings.ollama_base_url} -- skipping live SQL Agent test")
    return provider


@pytest.mark.live
@pytest.mark.db
@pytest.mark.asyncio
async def test_answer_question_live_openrouter_simple_count(require_ro_database, require_openrouter):
    answer = await answer_question("Berapa jumlah baris di tabel regions?", llm=require_openrouter)
    assert answer.success is True, answer.error
    assert answer.sql is not None
    assert answer.provider == "gemini"


@pytest.mark.live
@pytest.mark.db
@pytest.mark.asyncio
async def test_answer_question_live_ollama_simple_count(require_ro_database, require_ollama):
    answer = await answer_question("Berapa jumlah baris di tabel regions?", llm=require_ollama)
    assert answer.success is True, answer.error
    assert answer.sql is not None
    assert answer.provider == "ollama"


@pytest.mark.live
@pytest.mark.db
@pytest.mark.asyncio
async def test_answer_question_live_zero_rows(require_ro_database, require_openrouter):
    answer = await answer_question(
        "Tampilkan baris di tabel regions dengan region_id = 999999, sebuah nilai yang tidak mungkin ada",
        llm=require_openrouter,
    )
    assert answer.success is True, answer.error
    assert answer.row_count == 0


@pytest.mark.live
@pytest.mark.db
@pytest.mark.asyncio
async def test_answer_question_live_against_view(require_ro_database, require_openrouter):
    """Closes the gap noted in M4: describe_table/execute_sql were only
    tested against ordinary tables there, not `v_delivery_enriched`. The
    agent doesn't special-case views -- inspect_schema's allowlist query
    against information_schema.tables includes views alongside tables,
    so this proves that holds end-to-end too."""
    answer = await answer_question(
        "Ambil 3 baris pertama dari v_delivery_enriched, kolom delivery_id dan delivery_status saja",
        llm=require_openrouter,
    )
    assert answer.success is True, answer.error
    assert answer.sql is not None
    assert "v_delivery_enriched" in answer.sql
