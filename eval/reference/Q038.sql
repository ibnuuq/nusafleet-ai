-- Q038: Berapa rata-rata waktu pengiriman? (tanpa filter disebutkan eksplisit di pertanyaan)
-- JAWABAN BENAR HARUS menyadari & menyebutkan trap D1/A24: 2.97% baris delivered_at < dispatched_at
-- (bug sinkronisasi jam depot SMU-01) dan mengecualikannya -- bukan langsung AVG() mentah.
SELECT
  ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at-dispatched_at))/3600.0), 3) AS avg_naive_INCLUDING_bad_rows,
  ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at-dispatched_at))/3600.0) FILTER (WHERE delivered_at > dispatched_at), 3) AS avg_correct_EXCLUDING_bad_rows,
  COUNT(*) FILTER (WHERE delivered_at < dispatched_at) AS n_bad_rows,
  ROUND(COUNT(*) FILTER (WHERE delivered_at < dispatched_at)::numeric / COUNT(*) * 100, 2) AS pct_bad_rows
FROM fleet.deliveries WHERE status='delivered';
-- evaluasi: agent HARUS menyebut adanya baris bermasalah ini, idealnya memakai angka "correct"
