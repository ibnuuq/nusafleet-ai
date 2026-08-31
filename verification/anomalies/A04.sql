-- A04: driver B2 (bukan B2_UMUM) yang dipakai berulang di kendaraan tronton/tractor_head
-- -> failure rate & harsh_braking rate lebih tinggi
WITH heavy AS (
  SELECT dl.delivery_id, dl.driver_id, dl.status, dl.vehicle_id, dr.license_type
  FROM fleet.deliveries dl
  JOIN fleet.vehicles v ON v.vehicle_id = dl.vehicle_id
  JOIN fleet.vehicle_models vm ON vm.model_id = v.model_id
  JOIN fleet.drivers dr ON dr.driver_id = dl.driver_id
  WHERE vm.v_class IN ('tronton','tractor_head')
),
mismatch_drivers AS (
  -- driver B2 (bukan B2_UMUM) dengan >=15 delivery kendaraan berat -> pola mismatch sistematis
  SELECT driver_id FROM heavy WHERE license_type = 'B2'
  GROUP BY driver_id HAVING COUNT(*) >= 15
),
tagged AS (
  SELECT h.*, (h.driver_id IN (SELECT driver_id FROM mismatch_drivers)) AS is_mismatch
  FROM heavy h
),
hb AS (
  SELECT delivery_id, COUNT(*) AS n_hb FROM fleet.vehicle_events
  WHERE ev_type = 'harsh_braking' AND delivery_id IS NOT NULL GROUP BY delivery_id
)
SELECT
  COUNT(DISTINCT driver_id) FILTER (WHERE is_mismatch) AS n_mismatch_drivers,
  ROUND(AVG((status IN ('failed','returned'))::int) FILTER (WHERE is_mismatch), 4) AS fail_rate_mismatch,
  ROUND(AVG((status IN ('failed','returned'))::int) FILTER (WHERE NOT is_mismatch), 4) AS fail_rate_baseline,
  ROUND(AVG((status IN ('failed','returned'))::int) FILTER (WHERE is_mismatch) /
        NULLIF(AVG((status IN ('failed','returned'))::int) FILTER (WHERE NOT is_mismatch),0), 2) AS fail_ratio,
  ROUND(AVG(COALESCE(hb.n_hb,0)::numeric) FILTER (WHERE is_mismatch), 4) AS hb_rate_mismatch,
  ROUND(AVG(COALESCE(hb.n_hb,0)::numeric) FILTER (WHERE NOT is_mismatch), 4) AS hb_rate_baseline,
  CASE WHEN
    AVG((status IN ('failed','returned'))::int) FILTER (WHERE is_mismatch) >
    AVG((status IN ('failed','returned'))::int) FILTER (WHERE NOT is_mismatch) * 2.0
    AND COUNT(DISTINCT driver_id) FILTER (WHERE is_mismatch) BETWEEN 20 AND 60
  THEN 'PASS' ELSE 'FAIL' END AS status
FROM tagged t LEFT JOIN hb ON hb.delivery_id = t.delivery_id;
