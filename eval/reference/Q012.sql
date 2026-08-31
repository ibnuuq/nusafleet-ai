-- Q012: Depot mana dengan deviasi jarak rencana vs aktual terbesar?
SELECT lo.location_code AS origin_depot,
       ROUND(AVG(dl.actual_distance_km / NULLIF(dl.planned_distance_km,0)), 3) AS avg_actual_vs_planned_ratio
FROM fleet.deliveries dl
JOIN fleet.orders o ON o.order_id = dl.order_id
JOIN fleet.locations lo ON lo.location_id = o.origin_location_id
WHERE lo.loc_type = 'depot' AND dl.actual_distance_km IS NOT NULL
GROUP BY lo.location_code ORDER BY avg_actual_vs_planned_ratio DESC;
-- kunci: JTM-01 (A08)
