-- Q009: Bulan mana volume order tertinggi dan terendah?
SELECT EXTRACT(MONTH FROM order_date)::int AS month, COUNT(*) AS n_orders
FROM fleet.orders GROUP BY 1 ORDER BY 1;
-- kunci: bulan 3 (Maret, Ramadan/Idulfitri, A25) tertinggi; bulan 4 terendah
