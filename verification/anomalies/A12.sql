-- A12: musim hujan (Des-Feb) koridor Semarang<->Surabaya -> accident event rate lebih tinggi
WITH d AS (
  SELECT dl.delivery_id, dl.dispatched_at, lo.location_code AS origin_code, r.region_code AS dest_region
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations lo ON lo.location_id = o.origin_location_id
  JOIN fleet.locations ld ON ld.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = ld.region_id
  WHERE lo.location_code IN ('JTG-01','JTM-01') AND r.region_code IN ('JATENG','JATIM')
),
tagged AS (
  SELECT d.*, EXTRACT(MONTH FROM dispatched_at) IN (12,1,2) AS is_rainy FROM d
),
acc AS (
  SELECT delivery_id FROM fleet.vehicle_events WHERE ev_type = 'accident' AND delivery_id IS NOT NULL
)
SELECT
  ROUND(AVG((t.delivery_id IN (SELECT delivery_id FROM acc))::int) FILTER (WHERE is_rainy), 5) AS accident_rate_rainy,
  ROUND(AVG((t.delivery_id IN (SELECT delivery_id FROM acc))::int) FILTER (WHERE NOT is_rainy), 5) AS accident_rate_dry,
  ROUND(AVG((t.delivery_id IN (SELECT delivery_id FROM acc))::int) FILTER (WHERE is_rainy) /
        NULLIF(AVG((t.delivery_id IN (SELECT delivery_id FROM acc))::int) FILTER (WHERE NOT is_rainy),0), 2) AS ratio,
  CASE WHEN AVG((t.delivery_id IN (SELECT delivery_id FROM acc))::int) FILTER (WHERE is_rainy) >
            AVG((t.delivery_id IN (SELECT delivery_id FROM acc))::int) FILTER (WHERE NOT is_rainy) * 2.0
       THEN 'PASS' ELSE 'FAIL' END AS status
FROM tagged t;
