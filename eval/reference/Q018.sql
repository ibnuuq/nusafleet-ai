-- Q018: Segment customer mana yang paling sering melebihi SLA?
SELECT c.segment, c.tier,
       ROUND(AVG((dl.delivered_at > o.promised_delivery_at)::int)*100, 2) AS sla_breach_pct
FROM fleet.deliveries dl
JOIN fleet.orders o ON o.order_id = dl.order_id
JOIN fleet.customers c ON c.customer_id = o.customer_id
WHERE dl.status='delivered' AND dl.delivered_at > dl.dispatched_at
GROUP BY c.segment, c.tier ORDER BY sla_breach_pct DESC LIMIT 10;
-- CATATAN: query ini TIDAK menyurfacekan A10 dengan jelas -- platinum tier lain sudah
-- pakai SLA 24 jam sejak awal, jadi FMCG-platinum cuma "menyusul" ke level yang sama
-- setelah Juni. Sinyal A10 yang benar ada di perbandingan before/after (lihat Q025).
