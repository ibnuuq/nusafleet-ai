WITH m AS (SELECT EXTRACT(MONTH FROM order_date)::int AS month, COUNT(*) AS n FROM fleet.orders GROUP BY 1)
SELECT
  (SELECT month FROM m ORDER BY n DESC LIMIT 1) AS peak_month,
  (SELECT month FROM m ORDER BY n ASC LIMIT 1) AS trough_month,
  CASE WHEN (SELECT month FROM m ORDER BY n DESC LIMIT 1) = 3
        AND (SELECT month FROM m ORDER BY n ASC LIMIT 1) = 4
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM m LIMIT 1;
