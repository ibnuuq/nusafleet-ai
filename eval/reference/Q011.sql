-- Q011: Berapa failure rate per region? (basis: seluruh attempt, bukan seluruh order -- D3)
WITH d AS (
  SELECT dl.status, r.region_code
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations l ON l.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = l.region_id
)
SELECT region_code,
       COUNT(*) AS n_attempts,
       ROUND(AVG((status IN ('failed','returned'))::int)*100, 2) AS failure_rate_pct
FROM d GROUP BY region_code ORDER BY failure_rate_pct DESC;
