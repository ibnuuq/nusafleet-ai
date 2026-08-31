-- A09: delivery akhir pekan di SUMUT -> failure rate lebih tinggi (dominan customer_closed)
WITH d AS (
  SELECT dl.status, dl.failure_reason, EXTRACT(DOW FROM dl.dispatched_at) IN (0,6) AS is_weekend
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations ld ON ld.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = ld.region_id
  WHERE r.region_code = 'SUMUT'
)
SELECT
  ROUND(AVG((status IN ('failed','returned'))::int) FILTER (WHERE is_weekend), 4) AS fail_rate_weekend,
  ROUND(AVG((status IN ('failed','returned'))::int) FILTER (WHERE NOT is_weekend), 4) AS fail_rate_weekday,
  ROUND(AVG((status IN ('failed','returned'))::int) FILTER (WHERE is_weekend) /
        NULLIF(AVG((status IN ('failed','returned'))::int) FILTER (WHERE NOT is_weekend),0), 2) AS ratio,
  MODE() WITHIN GROUP (ORDER BY failure_reason) FILTER (WHERE is_weekend AND status IN ('failed','returned')) AS dominant_reason,
  CASE WHEN AVG((status IN ('failed','returned'))::int) FILTER (WHERE is_weekend) >
            AVG((status IN ('failed','returned'))::int) FILTER (WHERE NOT is_weekend) * 1.5
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM d;
