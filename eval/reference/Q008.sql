-- Q008: Bandingkan on-time rate Juli vs Agustus per region
WITH d AS (
  SELECT dl.delivery_id, o.promised_delivery_at, dl.delivered_at, r.region_code,
         EXTRACT(MONTH FROM dl.dispatched_at)::int AS month
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations l ON l.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = l.region_id
  WHERE dl.status = 'delivered' AND dl.delivered_at > dl.dispatched_at AND EXTRACT(MONTH FROM dl.dispatched_at) IN (7,8)
)
SELECT region_code,
  ROUND(AVG((delivered_at <= promised_delivery_at)::int) FILTER (WHERE month=7)*100,1) AS ontime_pct_jul,
  ROUND(AVG((delivered_at <= promised_delivery_at)::int) FILTER (WHERE month=8)*100,1) AS ontime_pct_aug
FROM d GROUP BY region_code ORDER BY 3 ASC;
