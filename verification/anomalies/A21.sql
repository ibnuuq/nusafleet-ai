-- A21: kepatuhan preventive maintenance workshop JABAR turun sejak Mei (performed_date IS NULL naik)
WITH mtc AS (
  SELECT m.maintenance_id, m.performed_date, EXTRACT(MONTH FROM m.scheduled_date)::int AS month
  FROM fleet.maintenance m
  JOIN fleet.locations w ON w.location_id = m.workshop_location_id
  JOIN fleet.regions r ON r.region_id = w.region_id
  WHERE r.region_code = 'JABAR' AND m.mtc_type = 'preventive'
)
SELECT
  ROUND(AVG((performed_date IS NOT NULL)::int) FILTER (WHERE month < 5), 3) AS compliance_before_may,
  ROUND(AVG((performed_date IS NOT NULL)::int) FILTER (WHERE month >= 5), 3) AS compliance_from_may,
  CASE WHEN AVG((performed_date IS NOT NULL)::int) FILTER (WHERE month >= 5) <
            AVG((performed_date IS NOT NULL)::int) FILTER (WHERE month < 5) * 0.85
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM mtc;
