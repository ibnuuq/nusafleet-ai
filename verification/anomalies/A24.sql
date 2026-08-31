-- A24 == trap D1: delivered_at < dispatched_at (bug sinkronisasi jam depot SMU-01)
SELECT
  COUNT(*) AS n_bad_timestamp_rows,
  ROUND(COUNT(*)::numeric / (SELECT COUNT(*) FROM fleet.deliveries) * 100, 2) AS pct_of_all_deliveries,
  CASE WHEN COUNT(*) > 1000 THEN 'PASS' ELSE 'FAIL' END AS status
FROM fleet.deliveries WHERE delivered_at < dispatched_at;
