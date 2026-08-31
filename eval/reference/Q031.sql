-- Q031 (skenario Definition of Done): Analyze why Jakarta's operational cost
-- increased in August. Investigate root cause, validate, and report.
-- kunci: A05 -- 3 penyebab (maintenance, fuel, overtime), volume TURUN (red herring negatif)
WITH dki_deliv AS (
  SELECT dl.*, EXTRACT(MONTH FROM dl.dispatched_at)::int AS month
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations ld ON ld.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = ld.region_id
  WHERE r.region_code = 'DKI'
),
dki_mtc AS (
  SELECT m.*, EXTRACT(MONTH FROM m.scheduled_date)::int AS month
  FROM fleet.maintenance m
  JOIN fleet.locations w ON w.location_id = m.workshop_location_id
  JOIN fleet.regions r ON r.region_id = w.region_id
  WHERE r.region_code = 'DKI' AND m.mtc_type = 'corrective'
)
SELECT
  SUM(delivery_cost_idr) FILTER (WHERE month=7) + (SELECT SUM(cost_idr) FROM dki_mtc WHERE month=7) AS op_cost_jul,
  SUM(delivery_cost_idr) FILTER (WHERE month=8) + (SELECT SUM(cost_idr) FROM dki_mtc WHERE month=8) AS op_cost_aug,
  SUM(fuel_cost_idr) FILTER (WHERE month=7) AS fuel_jul, SUM(fuel_cost_idr) FILTER (WHERE month=8) AS fuel_aug,
  SUM(overtime_cost_idr) FILTER (WHERE month=7) AS overtime_jul, SUM(overtime_cost_idr) FILTER (WHERE month=8) AS overtime_aug,
  (SELECT SUM(cost_idr) FROM dki_mtc WHERE month=7) AS maintenance_jul, (SELECT SUM(cost_idr) FROM dki_mtc WHERE month=8) AS maintenance_aug,
  COUNT(*) FILTER (WHERE month=7) AS volume_jul, COUNT(*) FILTER (WHERE month=8) AS volume_aug
FROM dki_deliv;
