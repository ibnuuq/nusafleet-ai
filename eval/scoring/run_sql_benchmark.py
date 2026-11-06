#!/usr/bin/env python3
"""
run_sql_benchmark.py -- score the SQL Agent (M5) against the 40 reference
questions.

Isolation: the agent only ever sees question text from
`eval/questions/questions.json`. This script (outside `src/`) is the only
place that reads `eval/reference/`, and only to score the agent afterwards.

Scoring
- Q001-Q038 (auto): run the reference SQL and the agent's SQL on the same
  database and compare result sets. PASS when they match as unordered
  multisets of rows, comparing values only (column names/order ignored),
  numbers with a relative tolerance. Analytical questions (multi-angle,
  "why ...") often have no single correct result shape, so a mismatch there
  is flagged for manual review instead of a hard FAIL.
- Q039-Q040 (refusal): the schema has no data for these; recorded as
  NEEDS_REVIEW with the agent's answer, to be judged against
  `eval/reference/Q0xx_refusal_criteria.md`.

Usage
    DATABASE_URL=postgresql://postgres:...@localhost:5432/nusafleet \
    python eval/scoring/run_sql_benchmark.py --provider gemini [--only Q001,Q002]

DATABASE_URL (admin, for reference SQL) is separate from the agent's
DATABASE_URL_RO in .env. Results go to eval/internal/benchmark_<provider>_<ts>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

QUESTIONS_FILE = REPO_ROOT / "eval" / "questions" / "questions.json"
REFERENCE_DIR = REPO_ROOT / "eval" / "reference"
OUT_DIR = REPO_ROOT / "eval" / "internal"

REFUSAL_IDS = {"Q039", "Q040"}
# Open-ended / multi-step questions: a result-set mismatch is not proof of a
# wrong answer, so these go to manual review rather than FAIL.
ANALYTICAL_IDS = {f"Q{i:03d}" for i in range(19, 39)}

REL_TOL = 1e-2
ABS_TOL = 1e-6


# ---------------------------------------------------------------- comparison
def _norm(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        try:
            return float(s)
        except ValueError:
            return s.lower()
    return str(v)


def _row_key(row) -> tuple:
    vals = [_norm(v) for v in row]
    # Sort values within a row so column order doesn't matter.
    return tuple(sorted(vals, key=lambda x: (type(x).__name__, str(x))))


def _vals_match(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _rows_match(r1: tuple, r2: tuple) -> bool:
    return len(r1) == len(r2) and all(_vals_match(a, b) for a, b in zip(r1, r2))


def results_match(ref_rows: list[tuple], agent_rows: list[tuple]) -> bool:
    """Unordered multiset comparison with numeric tolerance.

    If the agent returned extra columns, also accept a match on any
    same-width projection of the agent's columns."""
    if len(ref_rows) != len(agent_rows):
        return False
    if not ref_rows:
        return True
    ref_w, ag_w = len(ref_rows[0]), len(agent_rows[0])
    if ag_w < ref_w:
        return False

    def _cmp(agent_proj):
        ref_sorted = sorted((_row_key(r) for r in ref_rows), key=str)
        ag_sorted = sorted((_row_key(r) for r in agent_proj), key=str)
        if Counter(ref_sorted) == Counter(ag_sorted):
            return True
        return all(_rows_match(a, b) for a, b in zip(ref_sorted, ag_sorted))

    if ag_w == ref_w:
        return _cmp(agent_rows)
    from itertools import combinations
    if ag_w > 8:  # avoid combinatorial blow-up
        return False
    for cols in combinations(range(ag_w), ref_w):
        if _cmp([tuple(r[i] for i in cols) for r in agent_rows]):
            return True
    return False


# ---------------------------------------------------------------- db helpers
def _run_sql(conn, sql: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout = '60s'")
        cur.execute(sql)
        rows = cur.fetchall() if cur.description else []
    conn.rollback()  # never persist anything
    return [tuple(r) for r in rows]


# ---------------------------------------------------------------- main
async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None, help="gemini | ollama (default: LLM_PROVIDER)")
    ap.add_argument("--only", default=None, help="comma-separated ids, e.g. Q001,Q005")
    args = ap.parse_args()

    import psycopg2

    from src.agents.sql_agent import answer_question
    from src.models.llm import get_llm

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL (admin) is required to run reference SQL.", file=sys.stderr)
        return 2

    llm = get_llm(args.provider)
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))["questions"]
    if args.only:
        wanted = {q.strip() for q in args.only.split(",")}
        questions = [q for q in questions if q["id"] in wanted]

    conn = psycopg2.connect(db_url)
    results, t0 = [], time.time()

    for q in questions:
        qid = q["id"]
        rec = {"id": qid, "question": q["question"]}
        try:
            ans = await answer_question(q["question"], llm=llm)
        except Exception as e:  # provider failure, etc.
            rec.update(verdict="ERROR", error=f"{type(e).__name__}: {e}")
            results.append(rec)
            print(f"{qid}  ERROR  {rec['error'][:80]}")
            continue

        rec.update(
            agent_sql=ans.sql,
            agent_answer=ans.answer,
            agent_success=ans.success,
            attempts=ans.attempts,
        )

        if qid in REFUSAL_IDS:
            rec["verdict"] = "NEEDS_REVIEW"
        elif not ans.success or not ans.sql:
            rec["verdict"] = "FAIL"
            rec["reason"] = ans.error or "agent produced no SQL"
        else:
            try:
                ref_rows = _run_sql(conn, (REFERENCE_DIR / f"{qid}.sql").read_text(encoding="utf-8"))
                ag_rows = _run_sql(conn, ans.sql)
                rec["ref_row_count"], rec["agent_row_count"] = len(ref_rows), len(ag_rows)
                if results_match(ref_rows, ag_rows):
                    rec["verdict"] = "PASS"
                else:
                    rec["verdict"] = "NEEDS_REVIEW" if qid in ANALYTICAL_IDS else "FAIL"
                    rec["reason"] = "result set differs from reference"
            except Exception as e:
                conn.rollback()
                rec["verdict"] = "FAIL"
                rec["reason"] = f"{type(e).__name__}: {e}"

        results.append(rec)
        print(f"{qid}  {rec['verdict']:<12} attempts={ans.attempts}")

    conn.close()

    counts = Counter(r["verdict"] for r in results)
    auto = [r for r in results if r["id"] not in REFUSAL_IDS and r["id"] not in ANALYTICAL_IDS]
    auto_pass = sum(r["verdict"] == "PASS" for r in auto)
    summary = {
        "provider": llm.name,
        "model": getattr(llm, "model", None),
        "n_questions": len(results),
        "verdicts": dict(counts),
        "factual_accuracy": f"{auto_pass}/{len(auto)}" if auto else None,
        "elapsed_s": round(time.time() - t0, 1),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"benchmark_{llm.name}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print("\n" + json.dumps(summary, indent=2))
    print(f"Saved: {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
