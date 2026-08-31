-- Q020: Apakah ada hubungan antara maintenance overdue dan breakdown? (kunci: A03, ~6-22x)
WITH veh_status AS (
  SELECT vehicle_id, (odometer_km - last_service_odometer_km) > (service_interval_km * 1.25) AS is_overdue
  FROM fleet.vehicles
),
breakdown AS (
  SELECT vehicle_id, COUNT(*) FILTER (WHERE ev_type='breakdown') AS n_breakdown
  FROM fleet.vehicle_events GROUP BY vehicle_id
)
SELECT vs.is_overdue, ROUND(AVG(COALESCE(b.n_breakdown,0)),3) AS avg_breakdown_events
FROM veh_status vs LEFT JOIN breakdown b ON b.vehicle_id = vs.vehicle_id
GROUP BY vs.is_overdue;
