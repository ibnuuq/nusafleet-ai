-- A22: delivery malam (22:00-04:00): transit -12% (tod_factor bawaan) & fuel cost +9% (overspeed)
WITH d AS (
  SELECT dl.delivery_id, dl.fuel_cost_idr, dl.actual_distance_km,
         EXTRACT(HOUR FROM dl.dispatched_at) AS h,
         EXTRACT(EPOCH FROM (dl.delivered_at - dl.dispatched_at))/3600.0 AS transit_h
  FROM fleet.deliveries dl WHERE dl.status='delivered' AND dl.delivered_at > dl.dispatched_at
),
tagged AS (
  SELECT *, (h >= 22 OR h <= 4) AS is_night FROM d
)
SELECT
  ROUND(AVG(fuel_cost_idr / NULLIF(actual_distance_km,0)) FILTER (WHERE is_night), 1) AS fuel_per_km_night,
  ROUND(AVG(fuel_cost_idr / NULLIF(actual_distance_km,0)) FILTER (WHERE NOT is_night), 1) AS fuel_per_km_day,
  ROUND(AVG(fuel_cost_idr / NULLIF(actual_distance_km,0)) FILTER (WHERE is_night) /
        NULLIF(AVG(fuel_cost_idr / NULLIF(actual_distance_km,0)) FILTER (WHERE NOT is_night),0), 3) AS fuel_ratio,
  ROUND((SELECT COUNT(*) FROM fleet.vehicle_events WHERE ev_type='overspeed'
         AND delivery_id IN (SELECT delivery_id FROM tagged WHERE is_night))::numeric /
        NULLIF((SELECT COUNT(*) FROM tagged WHERE is_night),0), 3) AS overspeed_rate_night,
  CASE WHEN AVG(fuel_cost_idr / NULLIF(actual_distance_km,0)) FILTER (WHERE is_night) >
            AVG(fuel_cost_idr / NULLIF(actual_distance_km,0)) FILTER (WHERE NOT is_night) * 1.03
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM tagged;
