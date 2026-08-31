-- A11: workshop WS-07 -- repeat CORRECTIVE repair kendaraan sama DI WORKSHOP YANG SAMA
-- dalam <=14 hari, dibanding baseline workshop lain (definisi dipersempit
-- supaya bukan sekadar "kepadatan maintenance tahunan" yang membuat baseline
-- ikut tinggi -- ketahuan saat verifikasi pertama, repeat_rate_baseline 79%!)
WITH mtc AS (
  SELECT m.maintenance_id, m.vehicle_id, m.workshop_location_id, m.scheduled_date, l.location_code
  FROM fleet.maintenance m JOIN fleet.locations l ON l.location_id = m.workshop_location_id
  WHERE m.mtc_type = 'corrective'
),
repeat_flag AS (
  SELECT a.maintenance_id, a.location_code,
         EXISTS (
           SELECT 1 FROM mtc b
           WHERE b.vehicle_id = a.vehicle_id AND b.workshop_location_id = a.workshop_location_id
             AND b.maintenance_id <> a.maintenance_id
             AND ABS(b.scheduled_date - a.scheduled_date) <= 14
         ) AS is_repeat
  FROM mtc a
)
SELECT
  ROUND(AVG(is_repeat::int) FILTER (WHERE location_code = 'WS-07'), 4) AS repeat_rate_ws07,
  ROUND(AVG(is_repeat::int) FILTER (WHERE location_code <> 'WS-07'), 4) AS repeat_rate_baseline,
  CASE WHEN AVG(is_repeat::int) FILTER (WHERE location_code = 'WS-07') >
            AVG(is_repeat::int) FILTER (WHERE location_code <> 'WS-07') * 1.8
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM repeat_flag;
