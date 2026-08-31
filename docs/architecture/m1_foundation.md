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
