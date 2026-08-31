-- Q013: Bagaimana tren biaya maintenance per bulan?
SELECT EXTRACT(MONTH FROM scheduled_date)::int AS month,
       SUM(cost_idr) AS total_cost, COUNT(*) AS n_records
FROM fleet.maintenance WHERE performed_date IS NOT NULL
GROUP BY 1 ORDER BY 1;
