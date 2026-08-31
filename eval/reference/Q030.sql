-- Q030: Adakah metrik yang justru membaik di semester dua? (kunci: A23 tol baru JABAR Sep, A15 volume ecommerce)
WITH d AS (
  SELECT dl.actual_distance_km, EXTRACT(MONTH FROM dl.dispatched_at)::int AS month, r.region_code
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations l ON l.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = l.region_id
  WHERE r.region_code = 'JABAR' AND dl.status='delivered'
)
SELECT month, ROUND(AVG(actual_distance_km),1) AS avg_distance_km
FROM d WHERE month IN (8,9) GROUP BY month ORDER BY month;
-- kunci: jarak JABAR turun ~8% di September (tol baru, A23) -- ini perbaikan, bukan masalah
