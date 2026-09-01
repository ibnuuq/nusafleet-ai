# M1 — Foundation Architecture

## Layering

```
src/
├── config.py          Settings (pydantic-settings), get_settings()
├── logging_config.py  configure_logging(), get_logger()
├── models/
│   ├── schemas/        domain data: Agent, Tool, Task, TaskResult, RunState, Evidence
│   └── llm/             LLMProvider (ABC) + GeminiProvider + OllamaProvider + get_llm()
├── agents/             agent implementations           -- M2+
├── orchestrator/        planner + execution loop         -- M3+
├── tools/               tool implementations (e.g. SQL)  -- M2+
├── memory/              run/session memory               -- M2+
├── evidence/            evidence persistence              -- M2+
└── api/                 HTTP layer                        -- M2+ (M1 ships a stub only)
```

`models/schemas` and `models/llm` are separate concerns sharing one top-level
folder deliberately (see the M1 plan): `schemas` are Pydantic *domain* models,
`llm` are Pydantic-backed *language model* clients. Neither depends on the
other except `LLMResponse`/`LLMMessage`, which are plain data.

## LLMProvider contract

```python
class LLMProvider(ABC):
    name: ClassVar[str]
    async def generate(self, prompt, *, system=None, temperature=0.2, max_tokens=None) -> LLMResponse: ...
    async def health_check(self) -> bool: ...
```

Both `GeminiProvider` and `OllamaProvider` implement this contract identically
from the orchestrator's point of view. Constructors never touch the network or
require credentials -- a provider can always be instantiated; only `generate()`
can fail (raises `LLMError`). This is what lets the M1 test suite run with no
API key, no live Ollama, and no network access at all.

`get_llm(name=None)` (in `models/llm/factory.py`) is the only place that reads
`Settings` to decide which provider to build. Everything else takes an
`LLMProvider` as a parameter, never a provider name string.

### Why `GeminiProvider` calls openrouter.ai

`GeminiProvider` no longer wraps the native `google-genai` SDK -- it makes
plain `httpx` calls to OpenRouter's OpenAI-compatible chat completions
endpoint (`https://openrouter.ai/api/v1/chat/completions`). The class name
and the `get_llm("gemini")` selector are unchanged: what the orchestrator
picks is a *model family*, not a vendor endpoint.

The reason is purely which credential is available: the project has an
OpenRouter API key, not a native Google AI Studio key, and the two are not
interchangeable. Practical consequences:

- the model is addressed by an OpenRouter-style slug, `google/gemini-2.5-flash`,
  not the native `gemini-2.5-flash` -- this is the `GEMINI_MODEL` default in
  `src/config.py`;
- the env var carrying the credential is `OPENROUTER_API_KEY`
  (`Settings.openrouter_api_key`), not `GEMINI_API_KEY` -- there is no
  backward-compat alias, since nothing else depended on the old name yet;
- OpenRouter has two failure modes the native API doesn't surface the same
  way: HTTP 402 (insufficient credits) and HTTP 429 (rate limit). Both are
  mapped explicitly to `LLMQuotaExceededError` / `LLMRateLimitError` rather
  than falling through to the generic `LLMError`, so an orchestrator can
  react to "out of credits" differently from "server error."
- `google-genai` was removed from `pyproject.toml` entirely -- it was the
  sole reason it was a dependency.

### Exception hierarchy

```
LLMError(RuntimeError)          # base -- existing `except LLMError` still catches everything
├── LLMTimeoutError              # request exceeded its timeout
├── LLMResponseError             # HTTP 200 but body empty/malformed (not the same as an empty completion)
├── LLMModelNotFoundError        # model slug/id unknown to the provider (HTTP 404)
├── LLMRateLimitError            # HTTP 429 (OpenRouter-specific today)
└── LLMQuotaExceededError        # HTTP 402 insufficient credits (OpenRouter-specific today)
```

All five live in `models/llm/base.py`, shared by both providers, even though
rate-limit/quota only currently apply to OpenRouter -- the goal is that M4+
orchestration code can write one `except LLMRateLimitError` regardless of
which provider is behind `LLMProvider` at the time. A legitimately empty
completion (`text == ""`) is not an error in either provider; only a missing
`choices`/`message` structure raises `LLMResponseError`.

## Ground-truth isolation

`docs/internal/`, `eval/reference/`, `eval/internal/`, and `verification/`
contain the answer key for the dataset (`docs/internal/README_ISOLATION.md`).
The rule is architectural, and M1 enforces it three ways:

1. **Nothing in `src/` names those paths, with one narrow, documented
   exception.** Mentioning a path is itself information about where the
   answer key lives, so as a rule `src/` doesn't. `src/config.py` is the one
   exception: it contains a `field_validator` on `artifact_dir` whose sole
   job is to *reject* a value that would resolve into a ground-truth
   location -- a rejection rule can't avoid naming what it rejects. It never
   reads, joins, or exposes those paths' contents, only raises `ValueError`.
   `tests/test_ground_truth_isolation.py` excludes exactly this one file from
   its substring scan, with a comment explaining why, and separately proves
   the rejection actually fires.
2. **Runtime filesystem access is allowlist-based, not denylist-based, as
   the primary control.** The only writable/readable location `Settings`
   exposes is `artifact_dir` (default `./artifacts/`). Ground-truth folders
   are never a candidate because they were never added to the allowlist --
   there is no filter to bypass. The `config.py` validator in (1) is defense
   in depth on top of this, not a replacement for it: it exists because
   `artifact_dir` is externally configurable (`ARTIFACT_DIR` env var), so a
   misconfiguration (e.g. `ARTIFACT_DIR=../docs/internal`, or a `..`
   traversal that lands there after resolution) should fail loudly at
   startup rather than silently work.
3. **The checks operate on resolved paths, not raw strings.** The
   `artifact_dir` validator calls `.resolve()` before comparing, so a
   traversal like `docs/public/../internal` -- which does not contain the
   literal substring `docs/internal` -- is still caught.

`tests/test_ground_truth_isolation.py` is the enforcement mechanism: it greps
`src/**/*.py` (minus the one documented exception above) for forbidden path
substrings, dumps a loaded `Settings` and checks none of its values resolve
to a ground-truth path, exercises the `artifact_dir` validator directly
against real ground-truth paths and a resolve-only-catchable traversal, and
asserts the `api` service in `docker-compose.yml` still mounts only `./src`.
Any future change that violates isolation fails this test immediately, in
CI, before it reaches a running agent.

## Known limitation: isolation is static, not yet a runtime guard

Everything above is **static**: it scans source text and validates one
config field at process startup. That is sufficient for M1 because nothing
in this milestone accepts a path or query built from dynamic input --
there is no tool yet.

It stops being sufficient the moment M4/M5 build real tools (SQL Agent, a
file reader, etc.) that take a path or query derived from *dynamic* input,
including LLM output. None of the following would be caught by a static
substring scan:

- a path built at runtime via string concatenation/`os.path.join` from a
  base directory and an LLM-supplied fragment;
- a SQL query that ends up querying outside the `fleet` schema because of a
  credential or connection mistake, rather than because the query text
  mentions a forbidden table name;
- a path traversal that a naive filesystem tool accepts because it never
  calls `.resolve()` and checks the result against an allowed prefix.

**Definition of done for any M4/M5 tool that accepts a path or query from
dynamic input (including LLM output): it must apply a runtime guard of the
same shape as the `artifact_dir` validator above** -- resolve the fully
concrete path/target first, then check it against an explicit allowlist
prefix (or, for SQL, run under the `nusafleet_ro` role with `search_path`
pinned to `fleet, public`, as `schema.sql` already sets up) -- **not** a
grep/substring check against the request text. This is not implemented in
M1; it is a requirement to carry forward, not a suggestion.

**Status as of M4:** closed for the SQL/table-name case -- see "M4 — Tool
System" below. Still open for the filesystem case, because no tool in M4
touches the filesystem; the same allowlist-prefix shape (resolve, then
check against `artifact_dir`) is the requirement to carry forward into
whichever milestone adds one.

## Why no admin database DSN in `Settings`

`schema.sql` already defines a read-only Postgres role, `nusafleet_ro`
(`default_transaction_read_only = on`, `statement_timeout = 30s`). `Settings`
exposes exactly one database field, `database_url_ro`. There is intentionally
no `database_url` (admin/write) field: an agent built on top of `Settings`
structurally cannot obtain a write connection through config, regardless of
what the LLM tries to do. The admin DSN Phase 0 tooling uses
(`data/generator/load.py`, `verification/`, `eval/reference/`) stays outside
this config object entirely, passed via its own env var as it already is
today (see `run_all_gates.sh`).

## M4 — Tool System

`src/tools/` gives agents four primitives to talk to the `fleet` database:
`execute_sql`, `inspect_schema`, `describe_table`, `get_sample_rows`. Each
takes a Pydantic input model and returns a Pydantic result model (never a
raw string) -- see `src/tools/schemas.py`. Errors raise a small hierarchy
in `src/tools/base.py` (`ToolError` -> `ToolValidationError` /
`ToolPermissionError` / `ToolTimeoutError` / `ToolExecutionError`),
mirroring `LLMError` from M3 so an M5+ orchestrator can write one
`except ToolError` across both LLM and tool failures.

### Read-only is enforced by the database, not by us

`src/tools/base._ro_connection()` is the only place this package opens a
database connection, and it only ever uses `settings.database_url_ro`.
There is no code path to an admin/write DSN in `src/tools/` --
`tests/test_tools.py::test_tools_never_reference_admin_database_dsn` is a
tripwire against one being added later.

`execute_sql` has a prefix check (`^\s*(SELECT|WITH)`) that rejects an
obvious write before it costs a round trip, but that check is **not** the
security boundary and must not be read as one. The boundary is the
`nusafleet_ro` Postgres role (`default_transaction_read_only = on`,
`statement_timeout = 30s`, `search_path = fleet, public` -- schema.sql).
Proof, verified against the running database while building this
milestone:

- a plain `UPDATE`/`DROP` is stopped by the prefix check, before it
  reaches the database at all;
- `WITH x AS (DELETE FROM regions RETURNING *) SELECT * FROM x` **passes**
  the prefix check (it starts with `WITH`) and is rejected by Postgres
  itself with `ReadOnlySqlTransaction`;
- `SELECT 1; DROP TABLE regions;` also passes the prefix check and is
  also rejected by Postgres with `ReadOnlySqlTransaction` -- the table is
  unaffected;
- `SELECT * FROM pg_authid` (outside the `fleet` schema) is rejected with
  `InsufficientPrivilege` -- not because of `search_path` (which only
  affects *unqualified* names) but because the role was simply never
  granted `SELECT` on anything outside `fleet`.

Both `ReadOnlySqlTransaction` and `InsufficientPrivilege` map to
`ToolPermissionError`; `QueryCanceled` (the 30s `statement_timeout` firing)
maps to `ToolTimeoutError`. All three are exercised against the real
database in `tests/test_tools.py`.

### Runtime guard for dynamic `table_name` input

Closes the "Known limitation" above for the SQL case. `describe_table` and
`get_sample_rows` take a `table_name` that will eventually come from LLM
output; per the definition of done stated above, it is validated against
a live allowlist, not matched against request text:

1. `inspect_schema.fetch_table_allowlist()` queries
   `information_schema.tables WHERE table_schema = 'fleet'` on every call
   -- the allowlist is the live schema itself, so it can't drift and isn't
   a hardcoded list to maintain.
2. `table_name` is checked against that allowlist *before* it is used to
   build any query. An unknown or injection-shaped name (e.g.
   `regions"; DROP TABLE regions; --`) raises `ToolValidationError` and
   never reaches SQL construction.
3. Where a table name still has to appear as a SQL identifier
   (`get_sample_rows`'s `FROM`, which can't be parameterized the way a
   `WHERE` value can), it is quoted with `psycopg2.sql.Identifier`, never
   string-interpolated -- a second, independent layer on top of the
   allowlist check, in the same spirit as the `artifact_dir` validator.

`information_schema`/`pg_catalog` access is intentionally left open
through this same connection (it's what `inspect_schema`/`describe_table`
run against) -- a deliberate choice, not an oversight; it doesn't expose
anything beyond schema metadata, and cross-schema *data* access is still
blocked by the role's grants as shown above.

No M4 tool touches the filesystem, so the filesystem half of the "Known
limitation" section above is unchanged -- still open, carried forward.

## M5 — SQL Agent

`src/agents/sql_agent.py` is the first place `LLMProvider` (M3) and
`src/tools/` (M4) meet. One function, `answer_question(question, *, llm,
tools=DEFAULT_TOOLS, max_attempts=3, max_rows_for_llm=50,
max_chars_for_llm=12_000) -> SQLAgentAnswer`. No planner, no orchestrator,
no multi-agent -- both `llm` and `tools` (a `SQLAgentTools` dataclass
wrapping `execute_sql`/`inspect_schema`/`describe_table`) are call-time
dependencies so the same function runs against any `LLMProvider` and, in
tests, against fakes.

`SQLAgentAnswer` is its own Pydantic model, not `Task`/`TaskResult` from
`models/schemas/task.py` -- those assume a planner (`depends_on`,
`agent_id`) that M5 explicitly doesn't build. It does reuse `Evidence`
from M1 unchanged: one `EvidenceKind.SQL_QUERY` entry for the SQL that
ran, one `EvidenceKind.TABLE` entry for the (possibly truncated) result,
with `total_row_count`/`truncated` recorded in `content` so the
truncation fact travels with the evidence, not just the prose answer.

### Schema discovery without touching schema.sql

The agent never reads `schema.sql` or has it pasted into a prompt. It
calls `tools.inspect_schema()` once per question to build a compact
table/column summary, and, only when a self-debug retry references a
known table, `tools.describe_table()` for that table's full column
detail. Both go through M4's tools, which query the live
`information_schema` -- the same mechanism M4 uses for its own runtime
table-name allowlist.

### F11 -- context blow-up is mitigated at the agent layer, not in `execute_sql`

M4 left `execute_sql` deliberately unbounded (50,000 rows demonstrated
passing straight through in `tests/test_tools.py`); that's still true
here -- this milestone does not touch `src/tools/`. The truncation
required by F11 happens strictly *after* `execute_sql` returns and
*before* any prompt is built, in `_prepare_rows_for_llm()`: capped by row
count (`max_rows_for_llm`, default 50) *and* a serialized-character
budget (`max_chars_for_llm`, default 12,000, so a handful of wide rows
can't blow the budget before the row cap is even reached).

The cut is never silent:

- `SQLAgentAnswer.truncated` / `.row_count` / `.rows_sent_to_llm` are
  structured fields on the response -- a caller (or a test) can assert on
  the fact of truncation without parsing prose;
- the summarization prompt sent to the LLM carries an explicit
  `[PERINGATAN: hasil dipotong ...]` marker naming the true total and the
  count actually shown, with an instruction not to present the sample as
  the whole result;
- the truncation fact is also duplicated onto the `TABLE` evidence entry
  (`content["truncated"]`, `content["total_row_count"]`), so it survives
  independently of what the LLM's summary says.

`tests/test_sql_agent.py::test_answer_question_truncates_large_result_for_llm`
proves this against a fabricated 50,000-row result: the prompt actually
sent to the LLM stays under 20,000 characters (context does not scale
with row count), while `row_count` on the response still reports the true
50,000.

### F01 -- self-debug loop, bounded at 3 attempts

Each attempt: build a prompt (schema summary, plus any prior
attempt's SQL + error + `describe_table` detail for a table it
referenced) → `llm.generate()` → extract SQL from a fenced code block →
`tools.execute_sql()`. A `ToolError` (any subtype -- validation,
permission, timeout, execution) is caught, recorded, and fed back for the
next attempt; a table name found in the failed SQL (via a `FROM`/`JOIN`
regex, checked against the schema's own allowlist) triggers a
`describe_table` call so the repair prompt has real column detail, not
just the error text -- this is the literal "inspect schema → perbaiki"
required by F01.

After `max_attempts` (default 3) with no successful `execute_sql`, the
loop stops. `SQLAgentAnswer.success` is `False`, `.answer` is a
deterministic failure message built in code (not an LLM call) naming the
attempt count and the last error, and **no summarization call is ever
made** -- there is structurally nothing for the LLM to invent an answer
from. `LLMError` (provider timeout/rate-limit/etc.) is a different
failure mode and is not caught by this loop; it propagates to the caller
rather than being silently retried against a possibly-broken provider.

`tests/test_sql_agent.py` proves both directions: a fake `execute_sql`
that always fails exhausts exactly 3 attempts and reports honestly
(`test_answer_question_self_debug_loop_stops_at_max_attempts`), and one
that fails once then succeeds recovers on attempt 2, with the repair
prompt demonstrably carrying the `describe_table` detail
(`test_answer_question_self_debug_loop_recovers_on_retry`).

### F02 -- zero rows is a successful answer

A 0-row `execute_sql` result is not caught by the self-debug loop (it's
not a `ToolError`) and is not treated as failure -- `success` is `True`,
`row_count` is `0`, and the summarization prompt states explicitly that
the result was empty, instructing the LLM to say so plainly rather than
invent data.

### Guardrails unchanged

`answer_question` never opens a database connection or an LLM HTTP client
itself -- it only calls the `tools`/`llm` it's given, which (by default)
are M4's `execute_sql`/`inspect_schema`/`describe_table` and an
`LLMProvider` from `get_llm()`. Read-only enforcement (M4) and the
ground-truth isolation validator (M1, `src/config.py`) are untouched by
this milestone -- neither file was modified building the SQL Agent.
