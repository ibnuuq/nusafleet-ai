#!/usr/bin/env python3
"""
run_gate_0d.py -- jalankan seluruh verifikasi anomali (A01-A26) terhadap
database Postgres yang sudah di-load, cetak ringkasan PASS/FAIL, dan tulis
hasil mentah ke gate_0d_result.json (dipakai untuk menyusun ground-truth
manifest, lihat build_manifest.py).

Usage:
    DATABASE_URL=postgresql://user:pass@host:port/db python run_gate_0d.py
"""
import json
import os
import sys
import glob

import psycopg2
import psycopg2.extras

DB_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nusafleet")
SQL_DIR = os.path.join(os.path.dirname(__file__), "anomalies")

ANOMALY_IDS = [f"A{n:02d}" for n in range(1, 27)]


def run_query(conn, sql_path):
    with open(sql_path) as f:
        sql = f.read()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql)
    if cur.description is None:
        return None
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def main():
    conn = psycopg2.connect(DB_URL)
    results = {}
    n_pass, n_fail, n_error = 0, 0, 0

    for aid in ANOMALY_IDS:
        sql_path = os.path.join(SQL_DIR, f"{aid}.sql")
        if not os.path.exists(sql_path):
            results[aid] = {"status": "MISSING_SQL"}
            n_error += 1
            continue
        try:
            rows = run_query(conn, sql_path)
            conn.commit()
            status = None
            if rows:
                # A25 khusus: pakai file bantu A25_status.sql untuk status
                if aid == "A25":
                    status_rows = run_query(conn, os.path.join(SQL_DIR, "A25_status.sql"))
                    conn.commit()
                    status = status_rows[0]["status"] if status_rows else None
                    rows = status_rows
                elif aid == "A17":
                    # A17 red herring: PASS jika region tinggi (by design) semuanya
                    # lebih mahal dari SEMUA region baseline (bukan cuma top-4 rank)
                    target = {"SULSEL", "SUMUT", "SUMSEL", "BALI"}
                    prices = {r["region_code"]: r["avg_price_per_liter"] for r in rows}
                    target_prices = [prices[c] for c in target if c in prices]
                    baseline_prices = [v for k, v in prices.items() if k not in target]
                    status = "PASS" if target_prices and baseline_prices and min(target_prices) > max(baseline_prices) else "FAIL"
                else:
                    status = rows[0].get("status")
            results[aid] = {"status": status or "UNKNOWN", "detail": rows}
            if status == "PASS":
                n_pass += 1
            elif status == "FAIL":
                n_fail += 1
            else:
                n_error += 1
        except Exception as e:
            conn.rollback()
            results[aid] = {"status": "ERROR", "error": str(e)}
            n_error += 1

    print(f"{'ID':<6}{'STATUS':<10}DETAIL")
    print("-" * 90)
    for aid in ANOMALY_IDS:
        r = results[aid]
        detail = ""
        if r.get("detail"):
            d0 = r["detail"][0]
            detail = ", ".join(f"{k}={v}" for k, v in d0.items() if k != "status")
        elif r.get("error"):
            detail = r["error"][:80]
        print(f"{aid:<6}{r['status']:<10}{detail[:110]}")

    print("-" * 90)
    print(f"TOTAL: {n_pass}/26 PASS, {n_fail}/26 FAIL, {n_error}/26 ERROR/UNKNOWN")

    out_path = os.path.join(os.path.dirname(__file__), "gate_0d_result.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nHasil lengkap: {out_path}")

    conn.close()
    return 0 if (n_pass == 26) else 1


if __name__ == "__main__":
    sys.exit(main())
