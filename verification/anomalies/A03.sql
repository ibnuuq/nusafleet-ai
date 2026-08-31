-- A03: kendaraan overdue service (odometer - last_service > interval*1.25) -> breakdown rate lebih tinggi
WITH veh_status AS (
  SELECT vehicle_id,
         (odometer_km - last_service_odometer_km) > (service_interval_km * 1.25) AS is_overdue
  FROM fleet.vehicles
),
breakdown_count AS (
  SELECT ve.vehicle_id, COUNT(*) FILTER (WHERE ve.ev_type = 'breakdown') AS n_breakdown, COUNT(*) AS n_events
  FROM fleet.vehicle_events ve GROUP BY ve.vehicle_id
)
SELECT
  ROUND(AVG(bc.n_breakdown) FILTER (WHERE vs.is_overdue), 3) AS avg_breakdown_overdue,
  ROUND(AVG(bc.n_breakdown) FILTER (WHERE NOT vs.is_overdue), 3) AS avg_breakdown_normal,
  ROUND(AVG(bc.n_breakdown) FILTER (WHERE vs.is_overdue) / NULLIF(AVG(bc.n_breakdown) FILTER (WHERE NOT vs.is_overdue),0), 2) AS ratio,
  CASE WHEN AVG(bc.n_breakdown) FILTER (WHERE vs.is_overdue) >
            AVG(bc.n_breakdown) FILTER (WHERE NOT vs.is_overdue) * 2.0
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM veh_status vs LEFT JOIN breakdown_count bc ON bc.vehicle_id = vs.vehicle_id;
