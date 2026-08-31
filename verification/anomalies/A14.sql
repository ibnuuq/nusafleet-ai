-- A14: kendaraan >8 harsh_braking/1000km -> maintenance cost/km lebih tinggi
WITH hb AS (
  SELECT vehicle_id, COUNT(*) AS n_hb FROM fleet.vehicle_events WHERE ev_type = 'harsh_braking' GROUP BY vehicle_id
),
rate AS (
  SELECT v.vehicle_id, v.odometer_km, COALESCE(hb.n_hb,0) / NULLIF(v.odometer_km/1000.0,0) AS hb_per_1000km
  FROM fleet.vehicles v LEFT JOIN hb ON hb.vehicle_id = v.vehicle_id
),
grp AS (
  SELECT r.vehicle_id, (r.hb_per_1000km > 8) AS is_high FROM rate r
),
mtc AS (
  SELECT m.vehicle_id, SUM(m.cost_idr) AS total_cost, MAX(v.odometer_km) AS odo
  FROM fleet.maintenance m JOIN fleet.vehicles v ON v.vehicle_id = m.vehicle_id
  GROUP BY m.vehicle_id
)
SELECT
  COUNT(*) FILTER (WHERE is_high) AS n_high_hb_vehicles,
  ROUND(SUM(mtc.total_cost) FILTER (WHERE is_high) / NULLIF(SUM(mtc.odo) FILTER (WHERE is_high),0), 2) AS cost_per_km_high,
  ROUND(SUM(mtc.total_cost) FILTER (WHERE NOT is_high) / NULLIF(SUM(mtc.odo) FILTER (WHERE NOT is_high),0), 2) AS cost_per_km_normal,
  CASE WHEN SUM(mtc.total_cost) FILTER (WHERE is_high) / NULLIF(SUM(mtc.odo) FILTER (WHERE is_high),0) >
            SUM(mtc.total_cost) FILTER (WHERE NOT is_high) / NULLIF(SUM(mtc.odo) FILTER (WHERE NOT is_high),0) * 1.25
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM grp g JOIN mtc ON mtc.vehicle_id = g.vehicle_id;
