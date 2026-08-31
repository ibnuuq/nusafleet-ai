-- A07: odometer rollback (LAG window function) -- odometer turun dibanding transaksi sebelumnya
WITH seq AS (
  SELECT vehicle_id, fuel_id, transacted_at, odometer_km,
         LAG(odometer_km) OVER (PARTITION BY vehicle_id ORDER BY transacted_at) AS prev_odo
  FROM fleet.fuel_transactions
)
SELECT
  COUNT(*) AS n_rollback_events,
  COUNT(DISTINCT vehicle_id) AS n_vehicles_affected,
  CASE WHEN COUNT(*) > 10 THEN 'PASS' ELSE 'FAIL' END AS status
FROM seq WHERE prev_odo IS NOT NULL AND odometer_km < prev_odo;
