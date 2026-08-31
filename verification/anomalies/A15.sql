-- A15: lonjakan order tanggal kembar (9/9,10/10,11/11,12/12) segment ecommerce
WITH twin AS (
  SELECT order_date::date AS d, COUNT(*) AS n
  FROM fleet.orders
  WHERE order_date::date IN ('2025-09-09','2025-10-10','2025-11-11','2025-12-12')
  GROUP BY order_date::date
),
normal AS (
  SELECT AVG(daily_n) AS avg_daily FROM (
    SELECT order_date::date AS d, COUNT(*) AS daily_n FROM fleet.orders
    WHERE order_date::date NOT IN ('2025-09-09','2025-10-10','2025-11-11','2025-12-12')
    GROUP BY order_date::date
  ) x
)
SELECT
  ROUND(AVG(twin.n),0) AS avg_twin_date_volume,
  ROUND(normal.avg_daily,0) AS avg_normal_daily_volume,
  ROUND((AVG(twin.n)/normal.avg_daily - 1)*100,1) AS pct_increase,
  CASE WHEN AVG(twin.n) > normal.avg_daily * 1.5 THEN 'PASS' ELSE 'FAIL' END AS status
FROM twin, normal GROUP BY normal.avg_daily;
