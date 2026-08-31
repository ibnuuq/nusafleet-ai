-- Q016: Top 10 kendaraan dengan biaya operasional per km tertinggi
SELECT dl.vehicle_id, v.plate_number,
       ROUND(SUM(dl.delivery_cost_idr) / NULLIF(SUM(dl.actual_distance_km),0), 0) AS cost_per_km
FROM fleet.deliveries dl JOIN fleet.vehicles v ON v.vehicle_id = dl.vehicle_id
WHERE dl.actual_distance_km > 0
GROUP BY dl.vehicle_id, v.plate_number
HAVING SUM(dl.actual_distance_km) > 1000
ORDER BY cost_per_km DESC LIMIT 10;
