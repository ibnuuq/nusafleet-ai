-- Q033: Kenapa breakdown meningkat di Q3? (kunci: A21 -> A03, rantai dua tingkat)
WITH mtc_compliance AS (
  SELECT EXTRACT(MONTH FROM m.scheduled_date)::int AS month,
         AVG((m.performed_date IS NOT NULL)::int) AS compliance
  FROM fleet.maintenance m
  JOIN fleet.locations w ON w.location_id = m.workshop_location_id
  JOIN fleet.regions r ON r.region_id = w.region_id
  WHERE r.region_code = 'JABAR' AND m.mtc_type = 'preventive'
  GROUP BY 1
),
breakdown_by_month AS (
  SELECT EXTRACT(MONTH FROM occurred_at)::int AS month, COUNT(*) AS n_breakdown
  FROM fleet.vehicle_events WHERE ev_type = 'breakdown' GROUP BY 1
)
SELECT c.month, ROUND(c.compliance*100,1) AS preventive_compliance_pct_jabar, b.n_breakdown AS fleetwide_breakdown_events
FROM mtc_compliance c JOIN breakdown_by_month b ON b.month = c.month ORDER BY c.month;
-- kunci: kepatuhan JABAR turun sejak Mei -> breakdown naik dengan lag beberapa bulan (Q3)
