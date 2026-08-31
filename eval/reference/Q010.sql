-- Q010: Model kendaraan mana dengan km/liter terburuk di H2 (Jul-Des)?
-- CATATAN PENTING: RB-600/ST-450 secara STRUKTURAL memang paling boros (tractor_head/
-- tronton, nominal km/l rendah by design) -- itu BUKAN anomali, itu wajar. Sinyal A01
-- (GX-350 terdegradasi) baru terlihat lewat DELTA H1->H2 per model, bukan ranking absolut.
-- Reference ini menyediakan KEDUANYA supaya evaluator bisa membedakan "wajar" vs "anomali".
WITH kpl AS (
  SELECT ft.vehicle_id, vm.model_code, ft.liters, ft.odometer_km,
         LAG(ft.odometer_km) OVER (PARTITION BY ft.vehicle_id ORDER BY ft.transacted_at) AS prev_odo,
         EXTRACT(MONTH FROM ft.transacted_at)::int AS month
  FROM fleet.fuel_transactions ft
  JOIN fleet.vehicles v ON v.vehicle_id = ft.vehicle_id
  JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
),
per_model AS (
  SELECT model_code,
    AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE month<=6) AS kpl_h1,
    AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE month>=7) AS kpl_h2
  FROM kpl WHERE prev_odo IS NOT NULL AND odometer_km > prev_odo
  GROUP BY model_code
)
SELECT model_code, ROUND(kpl_h1,2) AS kpl_h1, ROUND(kpl_h2,2) AS kpl_h2_absolute_worst_ranking,
       ROUND((1 - kpl_h2/NULLIF(kpl_h1,0))*100, 1) AS pct_degradation_h1_to_h2
FROM per_model ORDER BY kpl_h2 ASC;
-- jawaban "terburuk secara absolut" = RB-600/ST-450 (wajar, struktural)
-- jawaban "anomali/terdegradasi" = GX-350 (satu-satunya dgn pct_degradation besar, A01)

-- Query kedua: jawaban BENAR untuk A01 butuh segmentasi lebih dalam --
-- degradasi HANYA terjadi pada GX-350 yang acquisition_date < 2023-01-01,
-- dan mulai Mei (bukan H1/H2 Jun). Mencampur unit lama+baru & potongan Jun
-- mengencerkan sinyal dari 9.8% jadi cuma 1.3% (lihat query pertama di atas).
WITH kpl AS (
  SELECT ft.vehicle_id, v.acquisition_date, ft.liters, ft.odometer_km,
         LAG(ft.odometer_km) OVER (PARTITION BY ft.vehicle_id ORDER BY ft.transacted_at) AS prev_odo,
         EXTRACT(MONTH FROM ft.transacted_at)::int AS month
  FROM fleet.fuel_transactions ft
  JOIN fleet.vehicles v ON v.vehicle_id = ft.vehicle_id
  JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
  WHERE vm.model_code = 'GX-350'
)
SELECT
  (acquisition_date < '2023-01-01') AS is_old_unit,
  ROUND(AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE month<5), 2) AS kpl_before_may,
  ROUND(AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE month>=5), 2) AS kpl_from_may,
  ROUND((1 - AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE month>=5) /
         NULLIF(AVG((odometer_km-prev_odo)::numeric/NULLIF(liters,0)) FILTER (WHERE month<5),0))*100, 1) AS pct_degradation
FROM kpl WHERE prev_odo IS NOT NULL AND odometer_km > prev_odo
GROUP BY is_old_unit;
