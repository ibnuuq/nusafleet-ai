# eval/internal/

Placeholder. Reserved for internal evaluation artifacts (e.g. run logs,
scoring intermediates) that are for the evaluator, not the agent under test.

**This folder is ground truth-adjacent.** Once populated, treat it under the
same isolation rule as `docs/internal/` and `eval/reference/`:
see `docs/internal/README_ISOLATION.md`. Nothing in `src/` may reference it.
