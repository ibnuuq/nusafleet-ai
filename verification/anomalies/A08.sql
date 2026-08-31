-- A08: Depot JTM-01 (Surabaya) under-estimate jarak sistematis (actual/planned lebih tinggi dari fleet)
WITH d AS (
  SELECT dl.delivery_id, dl.actual_distance_km, dl.planned_distance_km, lo.location_code AS origin_code
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations lo ON lo.location_id = o.origin_location_id
  WHERE dl.actual_distance_km IS NOT NULL AND dl.planned_distance_km > 0
)
SELECT
  ROUND(AVG(actual_distance_km/planned_distance_km) FILTER (WHERE origin_code='JTM-01'), 3) AS ratio_jtm01,
  ROUND(AVG(actual_distance_km/planned_distance_km) FILTER (WHERE origin_code<>'JTM-01'), 3) AS ratio_fleet,
  CASE WHEN AVG(actual_distance_km/planned_distance_km) FILTER (WHERE origin_code='JTM-01') >
            AVG(actual_distance_km/planned_distance_km) FILTER (WHERE origin_code<>'JTM-01') * 1.1
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM d;
