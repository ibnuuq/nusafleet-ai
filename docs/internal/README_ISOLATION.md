# docs/internal/ — GROUND TRUTH, BUKAN UNTUK AGENT

Folder ini berisi **kunci jawaban** dataset NusaFleet: file mana yang berisi
anomali apa, query verifikasi, dan hasil aktualnya.

## Aturan isolasi (WAJIB dibaca sebelum mulai M1)

1. **Jangan mount folder ini ke sandbox/tool milik SQL Agent, Analytics
   Agent, GIS Agent, Research Agent, atau Reviewer Agent manapun.**
2. **Jangan masukkan isi file di sini ke system prompt, context window, atau
   RAG index** yang bisa diakses oleh agent yang sedang dievaluasi.
3. File yang termasuk kategori ini:
   - `ground_truth_manifest.json` (isi lengkap: anomaly_id, SQL verifikasi,
     expected/actual signal, status)
   - Seluruh isi `verification/anomalies/*.sql` dan `verification/run_gate_0d.py`
   - Seluruh isi `eval/reference/*.sql` dan `eval/reference/Q039_refusal_criteria.md`,
     `Q040_refusal_criteria.md`
   - `data/post_inject_manifest.json` (parameter & hasil injeksi mentah)
4. Yang **BOLEH** diakses agent (ini "dunia" yang mereka investigasi):
   - `schema.sql` (struktur tabel -- termasuk role `nusafleet_ro` read-only)
   - Data di database `nusafleet` itu sendiri (lewat role `nusafleet_ro`)
   - `docker-compose.yml`, `.env.example`
5. Siapapun yang membangun M1 (orchestrator/agent) harus verifikasi secara
   eksplisit bahwa folder `docs/internal/`, `verification/`, dan
   `eval/reference/` **tidak** masuk ke volume/mount/context tool agent
   sebelum deployment pertama.

## Cara pakai manifest ini (untuk manusia/evaluator)

- `ground_truth_manifest.json` — satu entry per anomali (A01-A26), berisi
  SQL verifikasi lengkap + hasil aktual dari run terakhir.
- Untuk menjalankan ulang verifikasi: `verification/run_gate_0d.py` (Gate 0d)
  dan `eval/reference/run_reference_check.py` (Gate 0e).
- Regenerasi dataset: `data/generator/main.py` lalu `data/generator/load.py`.
