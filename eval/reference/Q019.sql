-- Q019: Kenapa failure rate di SUMUT lebih tinggi? (kunci: A09 -- akhir pekan, customer_closed)
WITH d AS (
  SELECT dl.status, dl.failure_reason, EXTRACT(DOW FROM dl.dispatched_at) IN (0,6) AS is_weekend
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations l ON l.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = l.region_id
  WHERE r.region_code = 'SUMUT'
)
SELECT is_weekend, COUNT(*) AS n,
       ROUND(AVG((status IN ('failed','returned'))::int)*100,2) AS failure_rate_pct,
       MODE() WITHIN GROUP (ORDER BY failure_reason) FILTER (WHERE status IN ('failed','returned')) AS dominant_reason
FROM d GROUP BY is_weekend;
