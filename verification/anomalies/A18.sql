-- A18: driver dengan total jam kerja >11 jam sehari -> insiden hari berikutnya naik
WITH d AS (
  SELECT delivery_id, driver_id, vehicle_id, dispatched_at::date AS work_date,
         EXTRACT(EPOCH FROM (arrived_at - dispatched_at))/3600.0 AS duration_h
  FROM fleet.deliveries WHERE arrived_at IS NOT NULL AND arrived_at > dispatched_at
),
daily AS (
  SELECT driver_id, work_date, SUM(duration_h) AS total_h FROM d GROUP BY driver_id, work_date
),
overwork AS (
  SELECT driver_id, work_date FROM daily WHERE total_h > 11
),
nextday AS (
  SELECT d.delivery_id, TRUE AS is_nextday
  FROM d JOIN overwork o ON o.driver_id = d.driver_id AND o.work_date = d.work_date - INTERVAL '1 day'
),
incident AS (
  SELECT DISTINCT delivery_id FROM fleet.vehicle_events
  WHERE ev_type IN ('harsh_braking','overspeed','accident') AND delivery_id IS NOT NULL
)
SELECT
  (SELECT COUNT(*) FROM overwork) AS n_overwork_driver_days,
  COUNT(*) AS n_nextday_deliveries,
  ROUND(AVG((d.delivery_id IN (SELECT delivery_id FROM incident))::int) FILTER (WHERE nd.is_nextday), 4) AS incident_rate_nextday,
  ROUND(AVG((d.delivery_id IN (SELECT delivery_id FROM incident))::int) FILTER (WHERE nd.is_nextday IS NULL), 4) AS incident_rate_baseline,
  CASE WHEN AVG((d.delivery_id IN (SELECT delivery_id FROM incident))::int) FILTER (WHERE nd.is_nextday) >
            AVG((d.delivery_id IN (SELECT delivery_id FROM incident))::int) FILTER (WHERE nd.is_nextday IS NULL) * 2.0
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM d LEFT JOIN nextday nd ON nd.delivery_id = d.delivery_id;
