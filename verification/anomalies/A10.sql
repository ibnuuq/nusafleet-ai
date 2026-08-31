-- A10: SLA platinum-FMCG diperketat 36->24 jam sejak 2025-06-01 -> breach rate naik meski transit stabil
WITH target AS (
  SELECT o.order_id, o.customer_id, o.promised_delivery_at, dl.delivered_at, dl.status,
         EXTRACT(MONTH FROM o.order_date)::int >= 6 AS after_june
  FROM fleet.orders o
  JOIN fleet.customers c ON c.customer_id = o.customer_id
  JOIN fleet.deliveries dl ON dl.order_id = o.order_id AND dl.status = 'delivered'
  WHERE c.tier = 'platinum' AND c.segment = 'fmcg'
)
SELECT
  ROUND(AVG((delivered_at > promised_delivery_at)::int) FILTER (WHERE NOT after_june), 4) AS breach_rate_before,
  ROUND(AVG((delivered_at > promised_delivery_at)::int) FILTER (WHERE after_june), 4) AS breach_rate_after,
  CASE WHEN AVG((delivered_at > promised_delivery_at)::int) FILTER (WHERE after_june) >
            AVG((delivered_at > promised_delivery_at)::int) FILTER (WHERE NOT after_june) * 1.5
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM target;
