-- A16: kendaraan tercatat delivery selama window maintenance yang berlangsung lama (>5 hari)
-- -- deteksi generik lewat overlap tanggal antara deliveries & maintenance per kendaraan,
-- tanpa bergantung pada anotasi manapun.
WITH mtc AS (
  SELECT vehicle_id, scheduled_date, COALESCE(performed_date, scheduled_date) AS end_date,
         COALESCE(performed_date, scheduled_date) - scheduled_date AS span_days
  FROM fleet.maintenance
  WHERE COALESCE(performed_date, scheduled_date) - scheduled_date > 5   -- window maintenance panjang, bukan servis rutin sehari
),
overlap AS (
  SELECT DISTINCT dl.delivery_id, dl.vehicle_id
  FROM fleet.deliveries dl
  JOIN mtc ON mtc.vehicle_id = dl.vehicle_id
  WHERE dl.dispatched_at::date BETWEEN mtc.scheduled_date AND mtc.end_date
)
SELECT
  COUNT(DISTINCT vehicle_id) AS n_vehicles_affected,
  COUNT(*) AS n_deliveries_overlapping,
  CASE WHEN COUNT(DISTINCT vehicle_id) >= 2 AND COUNT(*) >= 40 THEN 'PASS' ELSE 'FAIL' END AS status
FROM overlap;
