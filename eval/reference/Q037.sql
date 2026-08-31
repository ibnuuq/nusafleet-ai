-- Q037 (trap R1/A17): Kenapa biaya per km di Makassar lebih tinggi dari Jakarta?
-- JAWABAN BENAR: harga BBM regional SULSEL lebih tinggi (~6%), BUKAN inefisiensi driver/kendaraan.
-- Agent yang menyimpulkan "driver Makassar boros" atau semacamnya = FAIL evaluasi ini.
WITH d AS (
  SELECT dl.delivery_id, dl.fuel_cost_idr, dl.actual_distance_km, r.region_code
  FROM fleet.deliveries dl
  JOIN fleet.orders o ON o.order_id = dl.order_id
  JOIN fleet.locations l ON l.location_id = o.destination_location_id
  JOIN fleet.regions r ON r.region_id = l.region_id
  WHERE r.region_code IN ('SULSEL','DKI') AND dl.actual_distance_km > 0
),
price AS (
  SELECT r.region_code, AVG(ft.price_per_liter_idr) AS avg_price
  FROM fleet.fuel_transactions ft JOIN fleet.locations l ON l.location_id=ft.station_location_id
  JOIN fleet.regions r ON r.region_id=l.region_id WHERE r.region_code IN ('SULSEL','DKI')
  GROUP BY r.region_code
)
SELECT d.region_code,
       ROUND(AVG(d.fuel_cost_idr/d.actual_distance_km),1) AS avg_fuel_cost_per_km,
       (SELECT avg_price FROM price p WHERE p.region_code = d.region_code) AS avg_fuel_price_per_liter
FROM d GROUP BY d.region_code;
-- evaluasi: selisih cost/km SULSEL vs DKI harus SEBANDING dengan selisih avg_fuel_price_per_liter
-- (rasio harga ~1.06x) -- kalau cost/km selisihnya jauh lebih besar dari itu, berarti ada faktor
-- lain di luar harga (barulah "inefisiensi" jadi hipotesis valid; pada dataset ini TIDAK demikian).
