-- Q027: Adakah customer dengan masalah data alamat? (kunci: A19 -- CUST-04417)
SELECT c.customer_code, c.company_name, COUNT(*) AS n_address_not_found
FROM fleet.deliveries dl
JOIN fleet.orders o ON o.order_id = dl.order_id
JOIN fleet.customers c ON c.customer_id = o.customer_id
WHERE dl.failure_reason = 'address_not_found'
GROUP BY c.customer_code, c.company_name
ORDER BY n_address_not_found DESC LIMIT 10;
