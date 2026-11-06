# NusaFleet AI

Multi-agent investigation platform over a synthetic B2B logistics dataset
(NusaFleet Logistics). See `design_dataset_and_scenarios.md` for the dataset
design and `docs/internal/README_ISOLATION.md` for the ground-truth isolation
rule that governs everything in this repo.

## Status

- **Phase 0 (dataset foundation): COMPLETE.** 26/26 anomalies verified
  (Gate 0d), 40/40 reference questions verified (Gate 0e). See
  `run_all_gates.sh` and `verification/`, `eval/reference/`.
- **M1 (agent-runtime skeleton): COMPLETE.** Config, logging, domain
  schemas, test infrastructure.
- **M3 (LLM providers): COMPLETE.** Provider-agnostic `LLMProvider`
  contract with Gemini (via OpenRouter) and Ollama implementations.
- **M4 (tool system): COMPLETE.** Read-only database tools:
  `inspect_schema`, `describe_table`, `get_sample_rows`, `execute_sql`.
- **M5 (SQL Agent): COMPLETE.** Single agent that answers a
  natural-language question with SQL, a self-debug retry loop, and
  evidence attached to every answer.
- **Next:** benchmark the SQL Agent against the 40 reference questions,
  then the planner and multi-agent orchestration loop.

## Repository layout

```
data/generator/     Phase 0 -- dataset generator (seeded, deterministic). Do not modify casually.
verification/       Phase 0 -- Gate 0d anomaly verification. Ground truth.
eval/reference/     Phase 0 -- Gate 0e reference SQL for 40 questions. Ground truth.
docs/internal/      Phase 0 -- ground-truth manifest. Never exposed to agents.
schema.sql          Postgres+PostGIS schema, incl. read-only role `nusafleet_ro`.
run_all_gates.sh    Regenerate dataset + re-run Gate 0d/0e end to end.

src/                M1+ -- agent runtime (providers, tools, SQL Agent)
tests/              M1+ -- unit + smoke tests
docs/architecture/  M1+ -- architecture notes
eval/questions/     M2+ -- runtime question bank (no answers)
eval/internal/      M2+ -- internal eval artifacts (ground-truth-adjacent)
eval/scoring/       M2+ -- evaluation metrics
```

## Ground-truth isolation (read this before touching `src/`)

`docs/internal/`, `eval/reference/`, `eval/internal/`, and `verification/`
contain the answer key for the dataset. **No code under `src/` may reference,
mount, or load any of those paths — ever**, including to exclude them. Details
and rationale: `docs/internal/README_ISOLATION.md` and
`docs/architecture/m1_foundation.md`. `tests/test_ground_truth_isolation.py`
enforces this automatically; it must pass before any change is considered
done.

## Dev environment

Requires Python >= 3.11.

```bash
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Linux/macOS:           source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env   # fill in secrets locally; .env is gitignored
```

`.env` only needs to carry what the app actually reads: `APP_ENV`, `LOG_LEVEL`,
`LLM_PROVIDER`, `OPENROUTER_API_KEY`/`GEMINI_MODEL`, `OLLAMA_BASE_URL`/
`OLLAMA_MODEL`, `DATABASE_URL_RO`, `ARTIFACT_DIR`. Postgres admin credentials
and `RANDOM_SEED` belong to the Phase 0 tooling, not to the app config.

`GEMINI_API_KEY` is **not** used anymore -- `GeminiProvider` calls OpenRouter
now, not the native Gemini API, so it reads `OPENROUTER_API_KEY` (an
OpenRouter key) and expects `GEMINI_MODEL` in OpenRouter slug form, e.g.
`google/gemini-2.5-flash`. See "Why GeminiProvider calls openrouter.ai" in
`docs/architecture/m1_foundation.md`.

## Running the skeleton

```bash
python -m src.api.main
```

Loads config, sets up logging, and logs that the M1 skeleton is wired
correctly. No HTTP server yet (that's M2+); this only proves the plumbing
works end to end.

## Tests

```bash
pytest -v
```

Everything except `tests/test_llm_live.py` runs fully offline: no real API
key, no live Ollama, no live Postgres required. Notable suites:

- `tests/test_smoke.py` -- project imports, config loads, providers
  instantiate, schemas validate.
- `tests/test_config.py`, `tests/test_schemas.py`, `tests/test_llm_providers.py`
  -- unit coverage per module, providers exercised via `httpx.MockTransport`.
- `tests/test_ground_truth_isolation.py` -- the isolation tripwire described
  above. Run it on its own with `pytest tests/test_ground_truth_isolation.py -v`.
- `tests/test_llm_live.py` -- hits real endpoints. The OpenRouter test needs
  `OPENROUTER_API_KEY` (in `.env` or the environment) and the Ollama test
  needs a reachable Ollama instance; each **skips itself** (not a failure)
  when its prerequisite is missing. Run everything except these with
  `pytest -m "not live"`.

## Choosing an LLM provider

```python
from src.models.llm import get_llm

llm = get_llm("gemini")   # or get_llm("ollama"), or get_llm() to use LLM_PROVIDER from .env
response = await llm.generate("...", system="...")
```

Both providers implement the same `LLMProvider` contract
(`src/models/llm/base.py`) and can be instantiated without credentials;
failures surface at `generate()` time, not at construction time.

## Not built yet

Planner, autonomous loop, multi-agent execution, benchmark scoring,
HTTP API, UI. No LangGraph/CrewAI/PydanticAI, Redis/Celery or vector DB
by design so far.

## License

MIT -- see `LICENSE`.
