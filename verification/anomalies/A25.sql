-- A25: musiman -- peak Ramadan Maret, dead week April
SELECT
  EXTRACT(MONTH FROM order_date)::int AS month, COUNT(*) AS n_orders
FROM fleet.orders GROUP BY 1 ORDER BY 1;
-- status dicek manual: bulan 3 harus tertinggi, bulan 4 harus terendah (lihat query kedua)
