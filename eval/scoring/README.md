# eval/scoring/

`run_sql_benchmark.py` scores the SQL Agent (M5) on the 40 reference
questions:

- **Q001-Q018** (factual): agent result set vs reference result set,
  order-insensitive, 1% numeric tolerance -> PASS / FAIL.
- **Q019-Q038** (analytical): exact match -> PASS, otherwise NEEDS_REVIEW,
  since open-ended questions have no single correct result shape.
- **Q039-Q040** (refusal): NEEDS_REVIEW against `eval/reference/*_refusal_criteria.md`.

```bash
DATABASE_URL=postgresql://postgres:...@localhost:5432/nusafleet \
python eval/scoring/run_sql_benchmark.py --provider ollama --only Q001,Q002
```

The agent only receives question text from `eval/questions/questions.json`.
Results are written to `eval/internal/`. Root-cause recall, trap avoidance
and hallucination metrics (design doc section 10) are still to come.
