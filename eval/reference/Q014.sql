-- Q014: Berapa load factor rata-rata per class kendaraan?
SELECT vm.v_class,
       ROUND(AVG(o.weight_kg / NULLIF(vm.capacity_kg,0)), 3) AS avg_load_factor
FROM fleet.deliveries dl
JOIN fleet.orders o ON o.order_id = dl.order_id
JOIN fleet.vehicles v ON v.vehicle_id = dl.vehicle_id
JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
WHERE o.weight_kg > 0
GROUP BY vm.v_class ORDER BY avg_load_factor;
-- kunci: tronton ~41% (A20)
