-- A05: skenario Definition of Done -- DKI operational cost naik Agustus, 3 penyebab, volume TURUN (red herring)
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
),
agg AS (
  SELECT
    SUM(delivery_cost_idr) FILTER (WHERE month=7) AS delivery_jul,
    SUM(delivery_cost_idr) FILTER (WHERE month=8) AS delivery_aug,
    SUM(fuel_cost_idr) FILTER (WHERE month=7) AS fuel_jul, SUM(fuel_cost_idr) FILTER (WHERE month=8) AS fuel_aug,
    SUM(overtime_cost_idr) FILTER (WHERE month=7) AS ot_jul, SUM(overtime_cost_idr) FILTER (WHERE month=8) AS ot_aug,
    COUNT(*) FILTER (WHERE month=7) AS vol_jul, COUNT(*) FILTER (WHERE month=8) AS vol_aug
  FROM dki_deliv
),
magg AS (
  SELECT SUM(cost_idr) FILTER (WHERE month=7) AS mtc_jul, SUM(cost_idr) FILTER (WHERE month=8) AS mtc_aug
  FROM dki_mtc
)
SELECT
  (agg.delivery_jul + magg.mtc_jul) AS op_cost_jul,
  (agg.delivery_aug + magg.mtc_aug) AS op_cost_aug,
  ROUND((((agg.delivery_aug+magg.mtc_aug)::numeric/(agg.delivery_jul+magg.mtc_jul)) - 1)*100,1) AS mom_pct,
  ROUND(((agg.fuel_aug::numeric/agg.fuel_jul)-1)*100,1) AS fuel_pct_change,
  ROUND(((agg.ot_aug::numeric/NULLIF(agg.ot_jul,0))-1)*100,1) AS overtime_pct_change,
  ROUND(((magg.mtc_aug::numeric/magg.mtc_jul)-1)*100,1) AS maintenance_pct_change,
  ROUND(((agg.vol_aug::numeric/agg.vol_jul)-1)*100,1) AS volume_pct_change,
  CASE WHEN (agg.delivery_aug+magg.mtc_aug) > (agg.delivery_jul+magg.mtc_jul)   -- operational cost naik
        AND agg.fuel_aug > agg.fuel_jul                                          -- fuel naik (penyebab 1 valid)
        AND magg.mtc_aug > magg.mtc_jul                                          -- maintenance naik (penyebab 2 valid)
        AND agg.ot_aug > agg.ot_jul                                              -- overtime naik (penyebab 3 valid)
        AND agg.vol_aug < agg.vol_jul                                            -- volume TURUN (red herring negatif)
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM agg, magg;
