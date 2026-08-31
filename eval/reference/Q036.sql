-- Q036: Ringkasan eksekutif 3 risiko operasional terbesar + estimasi dampak rupiah
-- kunci: sintesis multi-anomali -- tidak ada satu query tunggal "benar", ini menguji sintesis.
-- reference berikut menyediakan 3 kandidat risiko dengan angka dampak, evaluator menilai
-- apakah agent memilih dari himpunan ini dan angkanya masuk toleransi.
SELECT 'A03: kendaraan overdue service -> breakdown 20x lipat' AS risk,
       (SELECT COUNT(*) FROM fleet.vehicles WHERE (odometer_km-last_service_odometer_km) > service_interval_km*1.25) AS n_vehicles_affected
UNION ALL
SELECT 'A11: workshop WS-07 repeat repair 32% vs baseline 3%',
       (SELECT COUNT(*) FROM fleet.maintenance m JOIN fleet.locations l ON l.location_id=m.workshop_location_id WHERE l.location_code='WS-07')
UNION ALL
SELECT 'A26: kendaraan umur >7 tahun, cost/km 2.1x lipat',
       (SELECT COUNT(*) FROM fleet.vehicles WHERE EXTRACT(YEAR FROM AGE('2025-12-31'::date, acquisition_date)) > 7);
