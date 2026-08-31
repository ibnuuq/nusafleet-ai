-- Q025: Kenapa SLA breach FMCG naik sejak Juni padahal transit time stabil? (kunci: A10)
WITH target AS (
  SELECT o.order_id, o.promised_delivery_at, dl.delivered_at, dl.dispatched_at,
         EXTRACT(MONTH FROM o.order_date)::int >= 6 AS after_june
  FROM fleet.orders o
  JOIN fleet.customers c ON c.customer_id = o.customer_id
  JOIN fleet.deliveries dl ON dl.order_id = o.order_id AND dl.status='delivered' AND dl.delivered_at > dl.dispatched_at
  WHERE c.tier='platinum' AND c.segment='fmcg'
)
SELECT after_june,
  ROUND(AVG((delivered_at > promised_delivery_at)::int)*100,1) AS breach_pct,
  ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at-dispatched_at))/3600.0),2) AS avg_transit_hours
FROM target GROUP BY after_june;
