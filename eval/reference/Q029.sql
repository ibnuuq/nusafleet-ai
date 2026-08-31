-- Q029: Depot mana yang kepatuhan preventive maintenance-nya menurun? (kunci: A21 -- Bandung/JABAR sejak Mei)
WITH mtc AS (
  SELECT m.performed_date, r.region_code, EXTRACT(MONTH FROM m.scheduled_date)::int AS month
  FROM fleet.maintenance m
  JOIN fleet.locations w ON w.location_id = m.workshop_location_id
  JOIN fleet.regions r ON r.region_id = w.region_id
  WHERE m.mtc_type = 'preventive'
)
SELECT region_code,
  ROUND(AVG((performed_date IS NOT NULL)::int) FILTER (WHERE month<5)*100,1) AS compliance_before_may,
  ROUND(AVG((performed_date IS NOT NULL)::int) FILTER (WHERE month>=5)*100,1) AS compliance_from_may
FROM mtc GROUP BY region_code ORDER BY 3 ASC;
