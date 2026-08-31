-- Q035: Kalau anggaran maintenance hanya cukup utk 100 kendaraan, mana yang diprioritaskan?
-- kunci: gabungan A03 (overdue) + A14 (harsh braking) + A26 (umur >7th)
WITH veh AS (
  SELECT vehicle_id, plate_number, odometer_km, last_service_odometer_km, service_interval_km,
         (odometer_km - last_service_odometer_km) > (service_interval_km*1.25) AS is_overdue,
         EXTRACT(YEAR FROM AGE('2025-12-31'::date, acquisition_date)) AS age_years
  FROM fleet.vehicles
),
hb AS (SELECT vehicle_id, COUNT(*) AS n_hb FROM fleet.vehicle_events WHERE ev_type='harsh_braking' GROUP BY vehicle_id),
breakdown AS (SELECT vehicle_id, COUNT(*) AS n_breakdown FROM fleet.vehicle_events WHERE ev_type='breakdown' GROUP BY vehicle_id)
SELECT v.vehicle_id, v.plate_number, v.is_overdue, v.age_years,
       COALESCE(hb.n_hb,0) AS n_harsh_braking, COALESCE(bd.n_breakdown,0) AS n_breakdown,
       (v.is_overdue::int*3 + (v.age_years>7)::int*2 + (COALESCE(hb.n_hb,0) > 8*v.odometer_km/1000.0)::int*2 + COALESCE(bd.n_breakdown,0)) AS risk_score
FROM veh v LEFT JOIN hb ON hb.vehicle_id=v.vehicle_id LEFT JOIN breakdown bd ON bd.vehicle_id=v.vehicle_id
ORDER BY risk_score DESC LIMIT 100;
