-- A17 (red herring): harga BBM regional SULSEL/SUMUT/SUMSEL/BALI lebih tinggi -> cost/km lebih tinggi
-- TAPI sepenuhnya dijelaskan oleh harga per liter, bukan inefisiensi driver/kendaraan
WITH region_price AS (
  SELECT r.region_code, AVG(ft.price_per_liter_idr) AS avg_price
  FROM fleet.fuel_transactions ft
  JOIN fleet.locations l ON l.location_id = ft.station_location_id
  JOIN fleet.regions r ON r.region_id = l.region_id
  GROUP BY r.region_code
)
SELECT region_code, ROUND(avg_price,0) AS avg_price_per_liter,
       ROUND(avg_price / (SELECT MIN(avg_price) FROM region_price), 3) AS relative_to_cheapest,
       CASE WHEN region_code IN ('SULSEL','SUMUT','SUMSEL','BALI') THEN 'higher-cost region (by design)' ELSE 'baseline' END AS note
FROM region_price ORDER BY avg_price DESC;
-- status PASS jika SULSEL/SUMUT/SUMSEL/BALI konsisten di atas region lain (dicek manual dari output di atas)
