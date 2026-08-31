-- Q022: Apakah ada indikasi penyalahgunaan fuel card? (kunci: A06 -- liters > kapasitas tank)
SELECT ft.fuel_id, v.plate_number, ft.liters, v.tank_capacity_liter, ft.transacted_at
FROM fleet.fuel_transactions ft JOIN fleet.vehicles v ON v.vehicle_id = ft.vehicle_id
WHERE ft.liters > v.tank_capacity_liter
ORDER BY (ft.liters - v.tank_capacity_liter) DESC LIMIT 30;
