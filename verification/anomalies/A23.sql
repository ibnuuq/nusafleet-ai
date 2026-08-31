-- A23 (positive anomaly): tol baru Cikampek-Palimanan sejak 1 Sep -> jarak & transit region JABAR turun
WITH d AS (
  SELECT dl.delivery_id, dl.actual_distance_km, dl.planned_distance_km,
         EXTRACT(EPOCH FROM (dl.delivered_at - dl.dispatched_at))/3600.0 AS transit_h,
         EXTRACT(MONTH FROM dl.dispatched_at)::int AS month
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations ld ON ld.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = ld.region_id
  WHERE r.region_code = 'JABAR' AND dl.status='delivered' AND dl.delivered_at > dl.dispatched_at
)
SELECT
  ROUND(AVG(actual_distance_km) FILTER (WHERE month = 8), 1) AS avg_distance_aug,
  ROUND(AVG(actual_distance_km) FILTER (WHERE month = 9), 1) AS avg_distance_sep,
  ROUND((AVG(actual_distance_km) FILTER (WHERE month=9) / NULLIF(AVG(actual_distance_km) FILTER (WHERE month=8),0) - 1)*100,1) AS pct_change_distance,
  CASE WHEN AVG(actual_distance_km) FILTER (WHERE month = 9) < AVG(actual_distance_km) FILTER (WHERE month = 8) * 0.95
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM d;
