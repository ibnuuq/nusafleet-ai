-- Q003: Berapa rata-rata transit time (jam) di seluruh armada?
-- WAJIB filter delivered_at > dispatched_at (trap D1/A24 -- 2.97% baris rusak)
SELECT ROUND(AVG(EXTRACT(EPOCH FROM (delivered_at - dispatched_at))/3600.0), 2) AS avg_transit_hours,
       COUNT(*) AS n_valid_rows,
       (SELECT COUNT(*) FROM fleet.deliveries WHERE delivered_at < dispatched_at) AS n_excluded_bad_rows
FROM fleet.deliveries
WHERE status = 'delivered' AND delivered_at > dispatched_at;
