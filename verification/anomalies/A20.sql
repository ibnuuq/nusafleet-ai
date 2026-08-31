-- A20: tronton load factor rendah (~41%), CDE overload >100% kapasitas pada ~8.1% delivery
WITH dv AS (
  SELECT dl.delivery_id, vm.v_class, vm.capacity_kg, o.weight_kg,
         o.weight_kg / NULLIF(vm.capacity_kg,0) AS load_factor
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.vehicles v ON v.vehicle_id = dl.vehicle_id
  JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
  WHERE o.weight_kg > 0
)
SELECT
  ROUND(AVG(load_factor) FILTER (WHERE v_class='tronton'), 3) AS tronton_avg_load_factor,
  ROUND(AVG((load_factor > 1.0)::int) FILTER (WHERE v_class='cde') * 100, 1) AS cde_overload_pct,
  CASE WHEN AVG(load_factor) FILTER (WHERE v_class='tronton') BETWEEN 0.30 AND 0.55
        AND AVG((load_factor > 1.0)::int) FILTER (WHERE v_class='cde') BETWEEN 0.04 AND 0.14
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM dv;
