-- Q026: Apakah gaya mengemudi memengaruhi biaya maintenance? (kunci: A14 -- harsh_braking/1000km)
WITH hb AS (
  SELECT vehicle_id, COUNT(*) AS n_hb FROM fleet.vehicle_events WHERE ev_type='harsh_braking' GROUP BY vehicle_id
),
rate AS (
  SELECT v.vehicle_id, COALESCE(hb.n_hb,0)/NULLIF(v.odometer_km/1000.0,0) AS hb_per_1000km
  FROM fleet.vehicles v LEFT JOIN hb ON hb.vehicle_id=v.vehicle_id
),
mtc AS (SELECT vehicle_id, SUM(cost_idr) AS total_cost FROM fleet.maintenance GROUP BY vehicle_id)
SELECT (r.hb_per_1000km > 8) AS is_aggressive_driving,
       ROUND(AVG(m.total_cost),0) AS avg_maintenance_cost
FROM rate r JOIN mtc m ON m.vehicle_id = r.vehicle_id
GROUP BY 1;
