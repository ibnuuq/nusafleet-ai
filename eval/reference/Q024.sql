-- Q024: Workshop mana yang kualitas perbaikannya paling rendah? (kunci: A11 -- WS-07)
WITH mtc AS (
  SELECT m.maintenance_id, m.vehicle_id, m.workshop_location_id, m.scheduled_date, l.location_code
  FROM fleet.maintenance m JOIN fleet.locations l ON l.location_id = m.workshop_location_id
  WHERE m.mtc_type = 'corrective'
),
repeat_flag AS (
  SELECT a.maintenance_id, a.location_code,
         EXISTS (SELECT 1 FROM mtc b WHERE b.vehicle_id=a.vehicle_id AND b.workshop_location_id=a.workshop_location_id
                 AND b.maintenance_id<>a.maintenance_id AND ABS(b.scheduled_date-a.scheduled_date)<=14) AS is_repeat
  FROM mtc a
)
SELECT location_code, COUNT(*) AS n_corrective, ROUND(AVG(is_repeat::int)*100,1) AS repeat_repair_pct
FROM repeat_flag GROUP BY location_code HAVING COUNT(*) >= 20 ORDER BY repeat_repair_pct DESC LIMIT 10;
