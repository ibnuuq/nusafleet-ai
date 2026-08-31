-- Q028: Apa dampak kelelahan driver terhadap insiden? (kunci: A18 -- lag 1 hari, overwork>11h)
WITH d AS (
  SELECT delivery_id, driver_id, dispatched_at::date AS work_date,
         EXTRACT(EPOCH FROM (arrived_at - dispatched_at))/3600.0 AS duration_h
  FROM fleet.deliveries WHERE arrived_at IS NOT NULL AND arrived_at > dispatched_at
),
daily AS (SELECT driver_id, work_date, SUM(duration_h) AS total_h FROM d GROUP BY driver_id, work_date),
overwork AS (SELECT driver_id, work_date FROM daily WHERE total_h > 11),
nextday AS (
  SELECT d.delivery_id FROM d JOIN overwork o ON o.driver_id=d.driver_id AND o.work_date = d.work_date - INTERVAL '1 day'
),
incident AS (SELECT DISTINCT delivery_id FROM fleet.vehicle_events WHERE ev_type IN ('harsh_braking','overspeed','accident') AND delivery_id IS NOT NULL)
SELECT
  (d.delivery_id IN (SELECT delivery_id FROM nextday)) AS is_day_after_overwork,
  ROUND(AVG((d.delivery_id IN (SELECT delivery_id FROM incident))::int)*100,1) AS incident_rate_pct
FROM d GROUP BY 1;
