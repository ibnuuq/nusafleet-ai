-- Q005: Top 10 customer berdasarkan jumlah order
SELECT c.customer_code, c.company_name, COUNT(*) AS n_orders
FROM fleet.orders o JOIN fleet.customers c ON c.customer_id = o.customer_id
GROUP BY c.customer_code, c.company_name
ORDER BY n_orders DESC LIMIT 10;
