-- A26: kendaraan umur >7 tahun -- biaya maintenance/km (km DIKENDARAI TAHUN 2025,
-- bukan odometer seumur hidup) lebih tinggi vs kendaraan umur <3 tahun.
-- Catatan: versi sebelumnya membagi cost tahun ini dengan odometer SEUMUR HIDUP
-- (vehicles.odometer_km) -- untuk kendaraan tua itu angka besar (sudah bertahun-tahun
-- dipakai), untuk kendaraan muda angka kecil (baru dibeli), sehingga rasionya
-- selalu terbalik terlepas dari cost aktual. Km tahun 2025 diestimasi dari
-- rentang odometer_km di fuel_transactions (yang sekarang kumulatif per
-- kendaraan & fisik konsisten, lihat facts.py gen_fuel_transactions).
WITH km_2025 AS (
  SELECT vehicle_id, MAX(odometer_km) - MIN(odometer_km) AS km_driven_2025
  FROM fleet.fuel_transactions GROUP BY vehicle_id
),
veh AS (
  SELECT vehicle_id, EXTRACT(YEAR FROM AGE('2025-12-31'::date, acquisition_date)) AS age_years
  FROM fleet.vehicles
),
vehicle_cost AS (
  SELECT vehicle_id, SUM(cost_idr) AS total_cost FROM fleet.maintenance GROUP BY vehicle_id
),
per_vehicle AS (
  SELECT veh.vehicle_id, veh.age_years, vc.total_cost / NULLIF(k.km_driven_2025,0) AS cost_per_km
  FROM veh
  JOIN vehicle_cost vc ON vc.vehicle_id = veh.vehicle_id
  JOIN km_2025 k ON k.vehicle_id = veh.vehicle_id
  WHERE k.km_driven_2025 > 500   -- buang kendaraan dengan data fuel terlalu sedikit utk estimasi wajar
)
SELECT
  ROUND(AVG(cost_per_km) FILTER (WHERE age_years > 7), 2) AS cost_per_km_old,
  ROUND(AVG(cost_per_km) FILTER (WHERE age_years < 3), 2) AS cost_per_km_young,
  ROUND(AVG(cost_per_km) FILTER (WHERE age_years > 7) / NULLIF(AVG(cost_per_km) FILTER (WHERE age_years < 3),0), 2) AS ratio,
  CASE WHEN AVG(cost_per_km) FILTER (WHERE age_years > 7) >
            AVG(cost_per_km) FILTER (WHERE age_years < 3) * 1.5
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM per_vehicle;
