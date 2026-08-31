-- Q023: Apakah ada data odometer yang tidak konsisten? (kunci: A07 -- rollback, LAG window function)
WITH seq AS (
  SELECT vehicle_id, fuel_id, transacted_at, odometer_km,
         LAG(odometer_km) OVER (PARTITION BY vehicle_id ORDER BY transacted_at) AS prev_odo
  FROM fleet.fuel_transactions
)
SELECT vehicle_id, fuel_id, transacted_at, prev_odo, odometer_km
FROM seq WHERE prev_odo IS NOT NULL AND odometer_km < prev_odo
ORDER BY vehicle_id, transacted_at;
