-- Q015: Hari apa dalam seminggu dengan failure rate tertinggi?
SELECT TO_CHAR(dispatched_at, 'Day') AS day_name, EXTRACT(DOW FROM dispatched_at)::int AS dow,
       ROUND(AVG((status IN ('failed','returned'))::int)*100, 2) AS failure_rate_pct
FROM fleet.deliveries
GROUP BY 1,2 ORDER BY 2;
-- kunci: akhir pekan (Sabtu/Minggu) lebih tinggi
