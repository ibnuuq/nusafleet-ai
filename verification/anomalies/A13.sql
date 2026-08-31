-- A13: 3 rest area menyerap idle_excess panjang -> delivery yang melewatinya lebih lama
-- deteksi generik: rest area mana saja yang paling sering direferensikan di metadata idle_excess
WITH idle_ra AS (
  SELECT delivery_id, (metadata->>'rest_area_location_id')::bigint AS ra_id,
         (metadata->>'idle_minutes')::numeric AS idle_minutes
  FROM fleet.vehicle_events
  WHERE ev_type = 'idle_excess' AND metadata ? 'rest_area_location_id'
),
top_ra AS (
  SELECT ra_id, COUNT(*) AS n FROM idle_ra GROUP BY ra_id ORDER BY n DESC LIMIT 3
),
flagged AS (
  SELECT dl.delivery_id, EXTRACT(EPOCH FROM (dl.delivered_at - dl.dispatched_at))/60.0 AS duration_min,
         (i.ra_id IS NOT NULL) AS passes_rest_area
  FROM fleet.deliveries dl
  LEFT JOIN idle_ra i ON i.delivery_id = dl.delivery_id AND i.ra_id IN (SELECT ra_id FROM top_ra)
  WHERE dl.status = 'delivered' AND dl.delivered_at > dl.dispatched_at
)
SELECT
  (SELECT COUNT(DISTINCT ra_id) FROM top_ra) AS n_rest_area_detected,
  ROUND(AVG((SELECT idle_minutes FROM idle_ra i2 WHERE i2.delivery_id = f.delivery_id LIMIT 1))
        FILTER (WHERE passes_rest_area), 1) AS avg_idle_minutes_flagged,
  COUNT(*) FILTER (WHERE passes_rest_area) AS n_flagged_deliveries,
  CASE WHEN (SELECT COUNT(DISTINCT ra_id) FROM top_ra) = 3
       AND (SELECT AVG(idle_minutes) FROM idle_ra) BETWEEN 30 AND 65
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM flagged f;
