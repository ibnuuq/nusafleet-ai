-- Q032: Kenapa konsumsi BBM armada naik di semester dua? (kunci: A01 volume-efisiensi vs kenaikan harga -- harus dipisah)
WITH kpl AS (
  SELECT vm.model_code, ft.liters, ft.odometer_km,
         LAG(ft.odometer_km) OVER (PARTITION BY ft.vehicle_id ORDER BY ft.transacted_at) AS prev_odo,
         EXTRACT(MONTH FROM ft.transacted_at)::int AS month, ft.price_per_liter_idr
  FROM fleet.fuel_transactions ft
  JOIN fleet.vehicles v ON v.vehicle_id = ft.vehicle_id
  JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
)
SELECT
  ROUND(AVG(price_per_liter_idr) FILTER (WHERE month<=6),0) AS avg_price_h1,
  ROUND(AVG(price_per_liter_idr) FILTER (WHERE month>=7),0) AS avg_price_h2,
  ROUND(AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE model_code='GX-350' AND month<=6),2) AS gx350_kpl_h1,
  ROUND(AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE model_code='GX-350' AND month>=7),2) AS gx350_kpl_h2
FROM kpl WHERE prev_odo IS NOT NULL AND odometer_km > prev_odo;
-- kunci: harga naik (semua model) DAN GX-350 tua makin boros (A01) -- dua efek terpisah, jangan dicampur jadi satu angka
