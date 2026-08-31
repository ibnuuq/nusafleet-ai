-- A02: koridor Cakung/Tanjung Priok macet mulai Agustus (delay aditif -> naik transit_hours)
WITH d AS (
  SELECT dl.delivery_id, dl.dispatched_at, dl.delivered_at,
         EXTRACT(EPOCH FROM (dl.delivered_at - dl.dispatched_at))/3600.0 AS transit_h,
         lo.location_code AS origin_code
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations lo ON lo.location_id = o.origin_location_id
  WHERE dl.status = 'delivered' AND dl.delivered_at > dl.dispatched_at
    AND lo.location_code IN ('JKT-01','JKT-02')
)
SELECT
  ROUND(AVG(transit_h) FILTER (WHERE EXTRACT(MONTH FROM dispatched_at) = 7), 2) AS avg_transit_jul,
  ROUND(AVG(transit_h) FILTER (WHERE EXTRACT(MONTH FROM dispatched_at) = 8), 2) AS avg_transit_aug,
  ROUND((AVG(transit_h) FILTER (WHERE EXTRACT(MONTH FROM dispatched_at) = 8) /
         NULLIF(AVG(transit_h) FILTER (WHERE EXTRACT(MONTH FROM dispatched_at) = 7),0) - 1) * 100, 1) AS pct_increase,
  CASE WHEN AVG(transit_h) FILTER (WHERE EXTRACT(MONTH FROM dispatched_at) = 8) >
            AVG(transit_h) FILTER (WHERE EXTRACT(MONTH FROM dispatched_at) = 7) * 1.15
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM d;
