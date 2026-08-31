-- Q021: Driver mana yang anomali, dan apa polanya? (kunci: A04 -- lisensi B2 di kendaraan berat)
WITH heavy AS (
  SELECT dl.delivery_id, dl.driver_id, dl.status, dr.license_type, dr.driver_code
  FROM fleet.deliveries dl
  JOIN fleet.vehicles v ON v.vehicle_id = dl.vehicle_id
  JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
  JOIN fleet.drivers dr ON dr.driver_id = dl.driver_id
  WHERE vm.v_class IN ('tronton','tractor_head')
)
SELECT driver_code, license_type, COUNT(*) AS n_heavy_deliveries,
       ROUND(AVG((status IN ('failed','returned'))::int)*100,1) AS failure_rate_pct
FROM heavy WHERE license_type = 'B2'
GROUP BY driver_code, license_type HAVING COUNT(*) >= 15
ORDER BY n_heavy_deliveries DESC LIMIT 50;
