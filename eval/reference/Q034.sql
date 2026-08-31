-- Q034: Delivery performance turun Agustus -- kenapa, berapa kontribusi tiap faktor?
-- kunci: A02 (koridor Cakung-Priok) dominan, BUKAN cuaca/volume
WITH d AS (
  SELECT dl.delivery_id, dl.dispatched_at, dl.delivered_at, lo.location_code AS origin_code,
         EXTRACT(EPOCH FROM (dl.delivered_at-dl.dispatched_at))/3600.0 AS transit_h
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations lo ON lo.location_id = o.origin_location_id
  WHERE dl.status='delivered' AND dl.delivered_at > dl.dispatched_at
)
SELECT
  origin_code IN ('JKT-01','JKT-02') AS is_corridor,
  EXTRACT(MONTH FROM dispatched_at)::int AS month,
  ROUND(AVG(transit_h),2) AS avg_transit_h, COUNT(*) AS n
FROM d WHERE EXTRACT(MONTH FROM dispatched_at) IN (7,8)
GROUP BY 1,2 ORDER BY 1,2;
