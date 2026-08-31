-- Q007: Region mana dengan delay tertinggi bulan Agustus?
-- "delay" = rata2 (delivered_at - promised_delivery_at) utk delivery yg lewat SLA
WITH d AS (
  SELECT dl.delivery_id, o.promised_delivery_at, dl.delivered_at, r.region_code
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations l ON l.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = l.region_id
  WHERE dl.status = 'delivered' AND dl.delivered_at > dl.dispatched_at
    AND EXTRACT(MONTH FROM dl.dispatched_at) = 8
)
SELECT region_code,
       ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at - promised_delivery_at))/3600.0) FILTER (WHERE delivered_at > promised_delivery_at), 2) AS avg_delay_hours_late_only,
       ROUND(AVG((delivered_at > promised_delivery_at)::int)*100, 1) AS pct_late
FROM d GROUP BY region_code ORDER BY pct_late DESC;
