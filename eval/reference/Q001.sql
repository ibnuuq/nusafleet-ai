-- Q001: Berapa total delivery yang berstatus delivered di 2025?
SELECT COUNT(*) AS total_delivered
FROM fleet.deliveries
WHERE status = 'delivered';
