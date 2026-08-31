-- A19: CUST-04417 -- lokasi tujuan tercatat salah, kontribusi besar terhadap address_not_found fleet-wide
WITH cust_fail AS (
  SELECT COUNT(*) AS n FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.customers c ON c.customer_id = o.customer_id
  WHERE c.customer_code = 'CUST-04417' AND dl.failure_reason = 'address_not_found'
),
fleet_fail AS (
  SELECT COUNT(*) AS n FROM fleet.deliveries WHERE failure_reason = 'address_not_found'
)
SELECT cust_fail.n AS cust_04417_address_not_found_count,
       fleet_fail.n AS fleet_wide_address_not_found_count,
       ROUND(cust_fail.n::numeric / NULLIF(fleet_fail.n,0) * 100, 1) AS pct_share,
       CASE WHEN cust_fail.n::numeric / NULLIF(fleet_fail.n,0) > 0.005 AND cust_fail.n > 5
            THEN 'PASS' ELSE 'FAIL' END AS status
FROM cust_fail, fleet_fail;
