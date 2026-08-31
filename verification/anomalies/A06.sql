-- A06: fuel card fraud -- liters melebihi kapasitas tank, atau transaksi ganda cepat di stasiun berjauhan
WITH over_capacity AS (
  SELECT ft.fuel_id, ft.vehicle_id FROM fleet.fuel_transactions ft
  JOIN fleet.vehicles v ON v.vehicle_id = ft.vehicle_id
  WHERE ft.liters > v.tank_capacity_liter
),
rapid_refuel AS (
  SELECT ft.fuel_id, ft.vehicle_id,
         LAG(ft.transacted_at) OVER (PARTITION BY ft.vehicle_id ORDER BY ft.transacted_at) AS prev_time,
         LAG(ft.station_location_id) OVER (PARTITION BY ft.vehicle_id ORDER BY ft.transacted_at) AS prev_station
  FROM fleet.fuel_transactions ft
)
SELECT
  (SELECT COUNT(*) FROM over_capacity) AS n_over_capacity_tx,
  (SELECT COUNT(DISTINCT vehicle_id) FROM over_capacity) AS n_vehicles_over_capacity,
  CASE WHEN (SELECT COUNT(*) FROM over_capacity) > 100
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM over_capacity LIMIT 1;
