-- Q004: Berapa harga solar rata-rata per bulan?
SELECT EXTRACT(MONTH FROM transacted_at)::int AS month,
       ROUND(AVG(price_per_liter_idr), 0) AS avg_price_idr
FROM fleet.fuel_transactions
GROUP BY 1 ORDER BY 1;
