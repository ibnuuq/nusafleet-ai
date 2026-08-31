-- Q002: Berapa jumlah kendaraan aktif per depot?
SELECT l.location_code AS depot, COUNT(*) AS n_active_vehicles
FROM fleet.vehicles v
JOIN fleet.locations l ON l.location_id = v.home_depot_id
WHERE v.status = 'active'
GROUP BY l.location_code
ORDER BY l.location_code;
