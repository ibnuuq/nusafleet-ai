-- A01: unit GX-350 (acquisition < 2023-01-01) degradasi efisiensi mulai Mei 2025
-- target: km/l turun ~16.7% (8.4 -> ~7.0) pada H2 dibanding sebelum Mei
WITH consumption AS (
  SELECT ft.vehicle_id, EXTRACT(MONTH FROM ft.transacted_at)::int AS month,
         ft.liters, LAG(ft.odometer_km) OVER (PARTITION BY ft.vehicle_id ORDER BY ft.transacted_at) AS prev_odo,
         ft.odometer_km
  FROM fleet.fuel_transactions ft
  JOIN fleet.vehicles v ON v.vehicle_id = ft.vehicle_id
  JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
  WHERE vm.model_code = 'GX-350' AND v.acquisition_date < '2023-01-01'
),
kpl AS (
  SELECT month, (odometer_km - prev_odo)::numeric / NULLIF(liters,0) AS km_per_liter
  FROM consumption WHERE prev_odo IS NOT NULL AND odometer_km > prev_odo
)
SELECT
  ROUND(AVG(km_per_liter) FILTER (WHERE month < 5), 2) AS kpl_before_may,
  ROUND(AVG(km_per_liter) FILTER (WHERE month >= 5), 2) AS kpl_from_may,
  ROUND((1 - AVG(km_per_liter) FILTER (WHERE month >= 5) / NULLIF(AVG(km_per_liter) FILTER (WHERE month < 5),0)) * 100, 1) AS pct_drop,
  CASE WHEN AVG(km_per_liter) FILTER (WHERE month >= 5) < AVG(km_per_liter) FILTER (WHERE month < 5) * 0.92
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM kpl;
