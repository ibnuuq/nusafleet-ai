#!/usr/bin/env bash
# run_all_gates.sh -- pipeline lengkap yang bisa dijalankan ulang kapan saja:
#   1. generate dataset (seeded, deterministic)
#   2. load ke Postgres+PostGIS
#   3. Gate 0d: verifikasi 26 anomali -> PASS/FAIL
#   4. Gate 0e: validasi 40 reference question -> OK/ERROR
#
# Exit code 0 hanya jika KEDUA gate PASS/OK penuh (26/26 dan 40/40).
#
# Usage:
#   DATABASE_URL=postgresql://user:pass@host:port/db ./run_all_gates.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5432/nusafleet}"

echo "================================================================"
echo "STEP 1/4: Generate dataset (seeded, deterministic)"
echo "================================================================"
cd "$ROOT_DIR/data/generator"
python3 main.py

echo
echo "================================================================"
echo "STEP 2/4: Load ke Postgres+PostGIS"
echo "================================================================"
DATABASE_URL="$DATABASE_URL" python3 load.py

echo
echo "================================================================"
echo "STEP 3/4: Gate 0d -- verifikasi 26 anomali"
echo "================================================================"
cd "$ROOT_DIR/verification"
GATE_0D_EXIT=0
DATABASE_URL="$DATABASE_URL" python3 run_gate_0d.py || GATE_0D_EXIT=$?

echo
echo "================================================================"
echo "STEP 4/4: Gate 0e -- validasi 40 reference question"
echo "================================================================"
cd "$ROOT_DIR/eval/reference"
GATE_0E_EXIT=0
DATABASE_URL="$DATABASE_URL" python3 run_reference_check.py || GATE_0E_EXIT=$?

echo
echo "================================================================"
echo "RINGKASAN"
echo "================================================================"
if [ "$GATE_0D_EXIT" -eq 0 ]; then
  echo "Gate 0d (26 anomali)       : PASS"
else
  echo "Gate 0d (26 anomali)       : FAIL -- cek verification/gate_0d_result.json"
fi
if [ "$GATE_0E_EXIT" -eq 0 ]; then
  echo "Gate 0e (40 reference question): PASS"
else
  echo "Gate 0e (40 reference question): FAIL -- cek eval/reference/reference_check_result.json"
fi

if [ "$GATE_0D_EXIT" -eq 0 ] && [ "$GATE_0E_EXIT" -eq 0 ]; then
  echo
  echo "GATE 0d + 0e: PASS. Siap lanjut ke tahap desain M1 (bukan berarti M1 sudah boleh mulai --"
  echo "keputusan itu tetap di luar scope skrip ini)."
  exit 0
else
  echo
  echo "GATE 0d dan/atau 0e: FAIL. JANGAN lanjut ke M1."
  exit 1
fi
