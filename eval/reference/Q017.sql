-- Q017: Berapa distribusi failure_reason?
SELECT failure_reason, COUNT(*) AS n,
       ROUND(COUNT(*)::numeric / SUM(COUNT(*)) OVER () * 100, 1) AS pct
FROM fleet.deliveries WHERE failure_reason IS NOT NULL
GROUP BY failure_reason ORDER BY n DESC;
