-- Q006: Berapa jumlah driver per tipe SIM?
SELECT license_type, COUNT(*) AS n_drivers
FROM fleet.drivers GROUP BY license_type ORDER BY license_type;
