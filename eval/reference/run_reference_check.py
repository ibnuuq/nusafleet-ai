#!/usr/bin/env python3
"""
run_reference_check.py -- jalankan Q001-Q038 terhadap database, pastikan
semuanya eksekusi tanpa error dan menghasilkan baris. Q039/Q040 dicek
terpisah (validasi bahwa tabel/kolom yang relevan memang tidak ada).
"""
import glob
import json
import os
import sys

import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nusafleet")
REF_DIR = os.path.dirname(__file__)


def main():
    conn = psycopg2.connect(DB_URL)
    results = {}
    n_ok, n_error = 0, 0

    for i in range(1, 39):
        qid = f"Q{i:03d}"
        path = os.path.join(REF_DIR, f"{qid}.sql")
        if not os.path.exists(path):
            results[qid] = {"status": "MISSING"}
            n_error += 1
            continue
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(open(path).read())
            conn.commit()
            rows = cur.fetchall() if cur.description else []
            results[qid] = {"status": "OK", "n_rows": len(rows), "sample": [dict(r) for r in rows[:3]]}
            n_ok += 1
        except Exception as e:
            conn.rollback()
            results[qid] = {"status": "ERROR", "error": str(e)}
            n_error += 1

    # Q039/Q040: validasi refusal criteria via bukti ketiadaan data
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='fleet'
        AND (column_name ILIKE '%%rain%%' OR column_name ILIKE '%%weather%%'
             OR column_name ILIKE '%%cuaca%%' OR column_name ILIKE '%%hujan%%'
             OR column_name ILIKE '%%temperature%%' OR column_name ILIKE '%%humid%%')
    """)
    weather_cols = cur.fetchone()[0]
    results["Q039"] = {"status": "OK" if weather_cols == 0 else "ERROR",
                        "evidence": f"weather-related columns found: {weather_cols} (expected 0)"}
    n_ok += 1 if weather_cols == 0 else 0
    n_error += 0 if weather_cols == 0 else 1

    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='fleet'
        AND (table_name ILIKE '%%invoice%%' OR table_name ILIKE '%%billing%%'
             OR table_name ILIKE '%%revenue%%' OR table_name ILIKE '%%pricing%%'
             OR table_name ILIKE '%%contract%%')
    """)
    revenue_tables = cur.fetchone()[0]
    results["Q040"] = {"status": "OK" if revenue_tables == 0 else "ERROR",
                        "evidence": f"revenue-related tables found: {revenue_tables} (expected 0)"}
    n_ok += 1 if revenue_tables == 0 else 0
    n_error += 0 if revenue_tables == 0 else 1

    print(f"{'ID':<8}{'STATUS':<10}DETAIL")
    print("-" * 100)
    for i in range(1, 41):
        qid = f"Q{i:03d}"
        r = results.get(qid, {"status": "MISSING"})
        detail = r.get("evidence") or (f"{r.get('n_rows','')} rows" if r["status"] == "OK" else r.get("error", "")[:80])
        print(f"{qid:<8}{r['status']:<10}{detail}")

    print("-" * 100)
    print(f"TOTAL: {n_ok}/40 OK, {n_error}/40 ERROR")

    with open(os.path.join(REF_DIR, "reference_check_result.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    conn.close()
    return 0 if n_ok == 40 else 1


if __name__ == "__main__":
    sys.exit(main())
