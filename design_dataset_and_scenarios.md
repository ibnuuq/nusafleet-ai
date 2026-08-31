# NusaFleet AI — Dataset & Investigation Scenario Design

**Status:** Step 0 (dikerjakan sebelum M1)
**Tujuan:** menetapkan "dunia" yang akan diinvestigasi AI, beserta kunci jawabannya, sebelum satu baris agent code ditulis.

Dokumen ini adalah *ground truth* project. Isi file ini **tidak boleh masuk ke prompt agent manapun**. Simpan di `docs/internal/`, dan pastikan folder itu di-exclude dari semua context loader.

---

## 1. Prinsip desain

1. **Setiap anomali punya jalur deteksi yang eksplisit.** Kalau saya tidak bisa menulis SQL untuk membuktikannya, anomali itu dibuang.
2. **Anomali berlapis, bukan single-cause.** Skenario utama (Definition of Done) sengaja punya 3 penyebab dengan bobot berbeda, supaya Reviewer Agent punya alasan nyata untuk REJECT kesimpulan tahap pertama.
3. **Ada red herring.** Kalau semua yang mencurigakan memang anomali, kita tidak pernah mengukur false positive.
4. **Ada data quality trap.** Query naif harus menghasilkan angka yang *salah tapi masuk akal*. Ini yang membedakan agent yang benar-benar inspect schema vs agent yang menebak.
5. **Deterministik.** `RANDOM_SEED = 20250101`. Regenerate harus menghasilkan dataset identik, kalau tidak angka evaluation tidak bisa dibandingkan antar-run.

---

## 2. Dunia: NusaFleet Logistics

Perusahaan logistik darat B2B Indonesia. Armada truk sendiri, 12 depot, layanan FTL/LTL antar kota di Jawa, Sumatera, Sulawesi, Bali.

**Window data:** `2025-01-01` s/d `2025-12-31` (12 bulan penuh).

Kenapa satu tahun penuh dan bukan rolling window: pertanyaan "Juli vs Agustus", "MoM", dan efek musiman butuh baseline sebelum-sesudah yang stabil. Rolling window bikin bulan pertama selalu terpotong.

**Mata uang:** IDR, integer (`bigint`), tanpa desimal.
**Timezone:** semua `timestamptz`, disimpan UTC, operasional Asia/Jakarta (UTC+7). Depot Makassar sengaja beroperasi di WITA — ini sumber trap D2 (lihat §7).

---

## 3. ERD

```text
                        regions
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
    locations          customers          (spatial ref)
        │                  │
        │                  ▼
        │               orders ──────────────┐
        │                  │                 │
        │                  ▼                 │
        │             deliveries ◄───────────┘
        │              │  │  │
        │              │  │  └──► drivers ──► (home_depot → locations)
        │              │  └─────► vehicles ──► vehicle_models
        │              │                │
        │              │                ├──► maintenance
        │              │                ├──► fuel_transactions
        │              │                └──► vehicle_events
        │                                        │
        └────────────────────────────────────────┘
                    (station / workshop / event geom)
```

Tabel di plan awal ada 9. Saya tambah **2 tabel referensi**: `regions` dan `vehicle_models`.

Alasannya bukan estetika: dua anomali inti (A01 fuel per model, A02 delay per region) mengharuskan agent melakukan join ke dimensi. Kalau `model_name` dan `region_name` cuma jadi kolom teks di `vehicles`/`locations`, agent bisa menjawab dengan `GROUP BY` satu tabel, dan kita kehilangan kemampuan menguji multi-hop join — yang justru jadi pembeda antara SQL Agent bagus dan SQL Agent asal.

---

## 4. Schema per tabel

DDL lengkap ada di `schema.sql`. Di bawah ini yang penting untuk generator dan untuk evaluation.

### 4.1 `regions` — 9 rows

| kolom | tipe | catatan |
|---|---|---|
| region_id | smallint PK | |
| region_code | text | `DKI`, `JABAR`, `BANTEN`, `JATENG`, `JATIM`, `SUMUT`, `SUMSEL`, `SULSEL`, `BALI` |
| region_name | text | |
| island | text | Jawa / Sumatera / Sulawesi / Bali |
| centroid | geography(Point,4326) | |
| congestion_index | numeric(3,2) | 0.85–1.45, dipakai generator untuk transit time |

Centroid: DKI (-6.20, 106.85), JABAR (-6.91, 107.61), BANTEN (-6.22, 106.63), JATENG (-6.97, 110.42), JATIM (-7.25, 112.75), SUMUT (3.59, 98.67), SUMSEL (-2.98, 104.76), SULSEL (-5.14, 119.42), BALI (-8.65, 115.22).

### 4.2 `locations` — 5.000 rows

| kolom | tipe | distribusi |
|---|---|---|
| location_id | bigint PK | |
| location_code | text UNIQUE | `LOC-000001` |
| name | text | |
| loc_type | enum | depot 12, workshop 18, fuel_station 220, rest_area 50, customer_site 4.700 |
| region_id | smallint FK | |
| address | text | |
| geom | geography(Point,4326) | sebaran normal radius 15–45 km dari centroid region |

12 depot: JKT-01 Cakung, JKT-02 Tanjung Priok, JKT-03 Cengkareng, BTN-01 Balaraja, JBR-01 Bandung, JBR-02 Cikarang, JTG-01 Semarang, JTM-01 Surabaya, JTM-02 Malang, SMU-01 Medan, SLS-01 Makassar, BLI-01 Denpasar.

### 4.3 `customers` — 10.000 rows

| kolom | tipe | distribusi |
|---|---|---|
| customer_id | bigint PK | |
| customer_code | text UNIQUE | `CUST-00001` |
| company_name | text | nama PT sintetis |
| segment | enum | fmcg 30%, manufacturing 25%, ecommerce 20%, retail 18%, pharma 7% |
| tier | enum | bronze 45%, silver 30%, gold 20%, platinum 5% |
| region_id | smallint FK | mengikuti bobot volume region (§5.1) |
| primary_location_id | bigint FK | salah satu customer_site di region-nya |
| contract_start_date | date | 2019-01-01 .. 2025-10-01 |
| sla_hours | smallint | bronze 72, silver 48, gold 36, platinum 24 |
| is_active | boolean | 94% true |

> `sla_hours` untuk platinum FMCG berubah 36 → 24 per `2025-06-01` (anomali A10). Nilai historis disimpan di `customer_sla_history` (tabel kecil, 3 kolom) supaya perubahan itu bisa ditemukan, bukan sekadar diasumsikan.

### 4.4 `vehicle_models` — 8 rows

Manufaktur **fiktif** (Garuda Motors, Sentosa Trucks, Rimba Auto, Nusantara Niaga) — supaya dataset tidak menyiratkan klaim performa tentang merek nyata.

| model_code | manufacturer | class | capacity_kg | nominal_km_per_liter |
|---|---|---|---|---|
| GX-200 | Garuda Motors | cdd | 4.000 | 9.2 |
| GX-350 | Garuda Motors | cde | 8.000 | 8.4 |
| ST-90 | Sentosa Trucks | van | 1.200 | 12.5 |
| ST-450 | Sentosa Trucks | tronton | 16.000 | 5.6 |
| RB-120 | Rimba Auto | wingbox | 7.500 | 7.8 |
| RB-600 | Rimba Auto | tractor_head | 24.000 | 4.2 |
| NV-75 | Nusantara Niaga | van | 1.000 | 13.1 |
| NT-300 | Nusantara Niaga | cde | 8.000 | 8.6 |

### 4.5 `vehicles` — 1.000 rows

| kolom | tipe | distribusi |
|---|---|---|
| vehicle_id | bigint PK | |
| plate_number | text UNIQUE | format plat wilayah sesuai depot |
| model_id | smallint FK | GX-350 22%, NT-300 18%, RB-120 15%, GX-200 14%, ST-450 12%, NV-75 8%, ST-90 7%, RB-600 4% |
| home_depot_id | bigint FK → locations | |
| acquisition_date | date | 2016-01-01 .. 2025-03-01, skew ke tahun baru |
| odometer_km | integer | fungsi umur × 62.000 km/tahun ± 18% |
| status | enum | active 88%, in_maintenance 9%, retired 3% |
| service_interval_km | integer | van 10.000, cdd/cde 15.000, tronton/wingbox 20.000, tractor_head 25.000 |
| last_service_odometer_km | integer | lihat A03 |
| tank_capacity_liter | smallint | van 60, cdd 100, cde 150, wingbox 150, tronton 200, tractor_head 400 |

`tank_capacity_liter` ada khusus supaya A06 (fuel fraud) punya batas fisik yang bisa dibuktikan.

### 4.6 `drivers` — 2.000 rows

| kolom | tipe | distribusi |
|---|---|---|
| driver_id | bigint PK | |
| driver_code | text UNIQUE | `DRV-0001` |
| full_name | text | |
| license_type | enum | `B1` 20%, `B2` 45%, `B2_UMUM` 35% |
| hire_date | date | 2015-01-01 .. 2025-09-01 |
| home_depot_id | bigint FK | |
| employment_status | enum | permanent 62%, contract 33%, resigned 5% |
| safety_score | numeric(4,1) | 0–100, mean 78, sd 11 |

Aturan bisnis (**tidak diberitahukan ke AI**): kendaraan class `tronton`/`tractor_head` seharusnya hanya dikemudikan pemegang `B2_UMUM`. Pelanggaran aturan ini adalah A04.

### 4.7 `orders` — 200.000 rows

| kolom | tipe | catatan |
|---|---|---|
| order_id | bigint PK | |
| order_code | text UNIQUE | `ORD-2025-000001` |
| customer_id | bigint FK | |
| order_date | timestamptz | distribusi §5.1 |
| requested_pickup_at | timestamptz | order_date + 4..36 jam |
| promised_delivery_at | timestamptz | requested_pickup_at + sla_hours (nilai SLA **saat itu**) |
| origin_location_id | bigint FK | depot terdekat |
| destination_location_id | bigint FK | customer_site |
| weight_kg | numeric(10,2) | lognormal, median 2.100, p95 11.500 |
| volume_m3 | numeric(8,2) | weight/densitas per segment |
| declared_value_idr | bigint | |
| priority | enum | standard 72%, express 23%, critical 5% |
| status | enum | delivered 91,2%, failed 4,1%, cancelled 2,4%, in_transit 2,3% |

### 4.8 `deliveries` — 200.000 rows

1 order = 0 atau 1 delivery. Order `cancelled` tidak punya delivery; sebagai gantinya ~4.800 order `delivered` punya **dua** baris delivery (percobaan pertama gagal → reattempt). Total tetap ±200k. Ini penting: agent yang menganggap relasi 1:1 akan salah hitung failure rate.

| kolom | tipe | catatan |
|---|---|---|
| delivery_id | bigint PK | |
| order_id | bigint FK | **bukan** unique |
| attempt_no | smallint | 1 atau 2 |
| vehicle_id, driver_id | bigint FK | |
| dispatched_at | timestamptz | |
| arrived_at | timestamptz | nullable |
| delivered_at | timestamptz | nullable jika failed |
| planned_distance_km | numeric(8,2) | |
| actual_distance_km | numeric(8,2) | |
| status | enum | delivered / failed / returned / cancelled |
| failure_reason | enum nullable | customer_closed, address_not_found, refused, vehicle_breakdown, document_issue |
| pod_signed | boolean | |
| delivery_cost_idr | bigint | fuel + toll + driver_allowance + overtime |
| route_geom | geography(LineString,4326) | disederhanakan: 4–8 titik |

**Definisi kanonik yang dipakai untuk menilai jawaban AI:**

```sql
-- transit time (jam)
EXTRACT(EPOCH FROM (delivered_at - dispatched_at)) / 3600.0
-- hanya untuk status='delivered' AND delivered_at > dispatched_at

-- on-time
delivered_at <= o.promised_delivery_at

-- failure rate
COUNT(*) FILTER (WHERE d.status IN ('failed','returned'))::numeric
  / NULLIF(COUNT(*), 0)   -- basis: seluruh attempt
```

### 4.9 `fuel_transactions` — 100.000 rows

| kolom | tipe | catatan |
|---|---|---|
| fuel_id | bigint PK | |
| vehicle_id, driver_id | bigint FK | |
| station_location_id | bigint FK | loc_type='fuel_station' |
| transacted_at | timestamptz | |
| liters | numeric(7,2) | 45–92% kapasitas tank |
| price_per_liter_idr | integer | §5.3 |
| total_cost_idr | bigint | `ROUND(liters * price_per_liter)` |
| odometer_km | integer | monoton naik per vehicle — **kecuali A07** |
| payment_method | enum | fuel_card 86%, cash 14% |

### 4.10 `maintenance` — 20.000 rows

| kolom | tipe | catatan |
|---|---|---|
| maintenance_id | bigint PK | |
| vehicle_id | bigint FK | |
| mtc_type | enum | preventive 61%, corrective 31%, inspection 8% |
| scheduled_date | date | |
| performed_date | date nullable | NULL = belum dikerjakan |
| odometer_km | integer | |
| workshop_location_id | bigint FK | |
| cost_idr | bigint | preventive median 1,8 jt; corrective median 2,6 jt (direvisi turun dari draf awal 7,4 jt — nilai itu membuat biaya maintenance regional per bulan lebih besar dari total biaya delivery, tidak realistis; lihat §6.1) |
| downtime_hours | numeric(6,1) | |
| notes | text | |

### 4.11 `vehicle_events` — 100.000 rows

| kolom | tipe | catatan |
|---|---|---|
| event_id | bigint PK | |
| vehicle_id | bigint FK | |
| driver_id | bigint FK nullable | |
| delivery_id | bigint FK nullable | ~78% terkait delivery |
| event_type | enum | harsh_braking 34%, overspeed 26%, idle_excess 19%, geofence_exit 9%, engine_fault 7%, breakdown 4%, accident 1% |
| occurred_at | timestamptz | |
| severity | smallint | 1–5 |
| geom | geography(Point,4326) | |
| metadata | jsonb | mis. `{"speed_kmh":94,"limit_kmh":70}` |

---

## 5. Distribusi & formula generator

### 5.1 Volume order

Bobot region (share dari 200k order): DKI 24%, JABAR 18%, JATIM 15%, JATENG 11%, BANTEN 10%, SUMUT 8%, SUMSEL 5%, SULSEL 5%, BALI 4%.

Multiplier bulanan (base = 1,00):

| Bln | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ×  | 0,92 | 0,89 | 1,48 | 0,71 | 0,97 | 1,03 | 1,05 | 1,04 | 1,12 | 1,18 | 1,26 | 1,35 |

Maret tinggi + April rendah = pola peak Ramadan/Idulfitri lalu dead week (A25). Sep–Des naik karena kampanye e-commerce (A15).

Hari: Sen–Jum 1,00; Sabtu 0,55; Minggu 0,18.
Jam pickup: bimodal, puncak 06:00–09:00 dan 19:00–22:00.

### 5.2 Transit time

```
base_hours    = distance_km / 45
region_factor = congestion_index (region tujuan)
tod_factor    = 1,25 jika dispatch 06:00–09:00 atau 16:00–19:00; 0,88 jika 22:00–04:00
noise         = lognormal(mu=0, sigma=0,22)

transit_hours = base_hours * region_factor * tod_factor * noise + dwell_time
dwell_time    = 0,4–1,8 jam (loading/unloading)
```

### 5.3 Harga BBM

Solar industri, base Rp 14.200/liter, naik bertahap:

| Periode | Harga |
|---|---|
| Jan–Mar | 14.200 |
| Apr–Jun | 14.650 |
| Jul | 14.900 |
| **Ags–Des** | **16.700** |

Kenaikan 12,1% per 1 Agustus adalah **penyebab yang paling gampang ditemukan** untuk skenario DoD — dan sengaja hanya menjelaskan sebagian kenaikan biaya. Agent yang berhenti di sini harus di-REJECT oleh Reviewer.

Faktor regional: SULSEL ×1,06, SUMUT ×1,04, SUMSEL ×1,03, BALI ×1,05, sisanya ×1,00. (Ini red herring R1.)

### 5.4 Konsumsi BBM

```
km_per_liter = model.nominal_km_per_liter
             * load_factor_penalty      -- 1,00 pada 50% muatan; 0,86 pada 100%
             * age_penalty              -- -1,2% per tahun umur kendaraan
             * driving_penalty          -- -0,8% per harsh_braking/1000km di atas 5
             * anomaly_multiplier       -- A01
             * lognormal(0, 0,09)
```

### 5.5 Biaya delivery

```
delivery_cost_idr = fuel_cost + toll_cost + driver_allowance + overtime_cost

fuel_cost        = (actual_distance_km / km_per_liter) * price_per_liter
toll_cost        = 850 * distance_km  jika rute antar kota (>60km), else 0
driver_allowance = 145.000 (antar-kota) / 45.000 (intra-region) + 22.000 per malam menginap
overtime_cost    = MAX(0, transit_hours - 5,0) * 40.000
```

Direvisi dari draf awal (allowance flat 145rb utk semua trip, overtime threshold 9 jam):
lihat catatan di §6.1 — allowance flat terlalu besar untuk trip lokal dan
mendominasi sinyal biaya; threshold 9 jam nyaris tidak pernah tercapai untuk
transit intra-kota yang basisnya 1–3 jam.

Struktur ini penting: `overtime_cost` adalah kanal yang menghubungkan **keterlambatan → biaya**, dan itu adalah penyebab kedua di skenario DoD. Tanpa kanal ini, root cause analysis-nya cuma satu lapis.

---

## 6. Katalog anomali tersembunyi (26)

Format: **ID — mekanisme — magnitudo — jalur deteksi — tier**.
Tier 1 = terlihat dari 1 tabel. Tier 2 = butuh join 2–3 tabel. Tier 3 = butuh korelasi/multi-hop + hipotesis.

| ID | Mekanisme | Magnitudo | Jalur deteksi | Tier |
|---|---|---|---|---|
| A01 | Unit **GX-350** yang `acquisition_date < 2023-01-01` mengalami degradasi efisiensi mulai Mei 2025 | km/l 8,4 → 7,0 (−16,7%) | `fuel_transactions` Δodometer / liters, `GROUP BY model_id, EXTRACT(YEAR FROM acquisition_date), month` | 2 |
| A02 | Koridor Cakung↔Tanjung Priok (DKI) macet mulai Agustus | transit +37%, hanya untuk order origin/dest di 2 depot itu | `deliveries` × `locations` × `regions`, filter pasangan depot | 2 |
| A03 | Kendaraan overdue service (`odometer − last_service_odometer > interval × 1,25`) | breakdown rate 6,1× | `vehicles` × `maintenance` × `vehicle_events` (breakdown) | 3 |
| A04 | 41 driver ber-lisensi `B2` ditugaskan ke `tronton`/`tractor_head` | failure rate 3,2×, harsh_braking 2,4× | `deliveries` × `drivers` × `vehicles` × `vehicle_models` | 3 |
| **A05** | **Lonjakan biaya operasional DKI Agustus — 3 penyebab** | **+28,4% MoM** | lihat §6.1 | **3** |
| A06 | 18 kendaraan: transaksi BBM > kapasitas tank, atau 2 transaksi <30 menit di stasiun berjarak >100 km | 214 transaksi janggal | `fuel_transactions` × `vehicles.tank_capacity_liter`; window function + `ST_Distance` | 3 |
| A07 | Odometer rollback pada 7 kendaraan | 31 kejadian | `LAG(odometer_km) OVER (PARTITION BY vehicle_id ORDER BY transacted_at)` | 2 |
| A08 | Depot JTM-01 Surabaya: `planned_distance` under-estimate sistematis | actual/planned = 1,22 vs 1,04 fleet-wide | `deliveries` `GROUP BY origin depot` | 1 |
| A09 | Delivery hari Sabtu/Minggu di SUMUT | failure rate 2,5×, dominan `customer_closed` | `deliveries` × `locations`, `EXTRACT(DOW ...)` | 2 |
| A10 | SLA platinum-FMCG diperketat 36h → 24h per 2025-06-01 | SLA breach 9% → 31% tanpa perubahan transit time | `orders` × `customers` × `customer_sla_history` | 3 |
| A11 | Workshop `WS-07` (Bandung): repeat repair kendaraan sama dalam ≤14 hari | 23% vs 6% baseline | self-join `maintenance` | 2 |
| A12 | Musim hujan (Des–Feb) koridor Semarang–Surabaya | accident event 2,8× | `vehicle_events` × bulan × `ST_Within(geom, corridor)` | 2 |
| A13 | 3 rest area menyerap `idle_excess` panjang | +47 menit rata-rata per delivery yang melewatinya | `vehicle_events` (idle_excess) × `locations` spatial join | 2 |
| A14 | Kendaraan dengan >8 harsh_braking/1000 km | biaya maintenance/km +40% | `vehicle_events` agregat × `maintenance` | 3 |
| A15 | Order spike tanggal 9/9, 10/10, 11/11, 12/12 (segment ecommerce) | volume harian +180% | `orders` × `customers.segment` | 1 |
| A16 | 2 kendaraan tercatat delivery saat `status='in_maintenance'` dan periodenya overlap dengan `maintenance` | 44 delivery | `deliveries` × `maintenance` overlap check | 3 |
| A17 | *(red herring R1)* Harga BBM regional SULSEL/SUMUT/BALI lebih tinggi | cost/km +4–6% | — biaya lebih tinggi tapi **wajar**, bukan inefisiensi | — |
| A18 | Driver dengan hari kerja >11 jam → insiden hari berikutnya | 3,1× | butuh window function lag-1-hari pada `deliveries` | 3 |
| A19 | `CUST-04417` punya koordinat destinasi salah (offset 12,4 km) | 38% dari `address_not_found` fleet-wide | `deliveries` failure × `ST_Distance(route end, destination geom)` | 3 |
| A20 | Tronton load factor rata-rata 41%; CDE overload >100% pada 8,1% order | misalokasi armada | `orders.weight_kg` / `vehicle_models.capacity_kg` | 2 |
| A21 | Kepatuhan preventive maintenance depot Bandung turun 88% → 61% mulai Mei | menjadi hulu dari A03 | `maintenance` `performed_date IS NULL` rate per depot per bulan | 3 |
| A22 | Delivery malam (dispatch 22:00–04:00) | transit −12% tapi konsumsi BBM +9% (overspeed) | trade-off, bukan murni anomali | 3 |
| A23 | *(positive anomaly)* Tol baru koridor Cikampek–Palimanan per 1 Sep | actual_distance −8%, transit −14% | agent harus melaporkan perbaikan, bukan hanya masalah | 2 |
| A24 | *(trap D1)* 3,1% delivery punya `delivered_at < dispatched_at` (bug sinkronisasi jam depot SMU-01) | AVG transit turun ±0,7 jam kalau tidak difilter | — | trap |
| A25 | Peak Ramadan Maret (+48%) lalu dead week April (−29%) | musiman | `orders` per bulan | 1 |
| A26 | Kendaraan umur >7 tahun: biaya maintenance/km naik non-linear | +2,1× vs armada <3 tahun | `vehicles.acquisition_date` × `maintenance` | 2 |

### 6.1 A05 — skenario Definition of Done

Pertanyaan target:

> *"Analyze why Jakarta's operational cost increased in August. Investigate the root cause, validate your conclusion, and create a report."*

> **Catatan revisi (setelah verifikasi empiris — lihat §11, gerbang 0d):** tabel di
> bawah awalnya berisi angka tebakan yang saya tulis sebelum generator ada.
> Setelah generator dijalankan dan hasilnya diverifikasi lewat SQL/pandas
> langsung terhadap data yang benar-benar dihasilkan, angkanya diganti dengan
> **angka aktual**, dan definisi "operational cost" dipersempit menjadi
> `delivery_cost (fuel+toll+allowance+overtime) + corrective maintenance cost`
> agar konsisten dengan apa yang bisa dibuktikan lewat query. Dua bug desain
> ditemukan dan diperbaiki di generator dalam proses ini:
> 1. Mask A02 awalnya mensyaratkan *asal dan tujuan* delivery sama-sama depot —
>    padahal tujuan selalu `customer_site`, sehingga anomali itu tidak pernah
>    tersuntik ke data. Diperbaiki: berlaku untuk delivery yang **berangkat**
>    dari Cakung/Tanjung Priok, sebagai delay aditif (bukan pengali), karena
>    basis transit intra-kota terlalu pendek untuk pengali kecil menembus
>    ambang overtime.
> 2. Allowance harian flat Rp145rb berlaku untuk semua trip termasuk
>    last-mile lokal DKI, membuatnya jadi komponen biaya terbesar yang murni
>    mengikuti volume order — sehingga menutupi sinyal dari fuel/overtime/
>    maintenance saat volume turun. Diperbaiki: allowance intra-region
>    diturunkan ke Rp45rb, hanya trip antar-kota (>60 km) yang dapat Rp145rb.

Kenaikan operational cost DKI Agustus vs Juli (angka aktual dari dataset ter-generate, seed `20250101`):

| Penyebab | Kontribusi thd kenaikan | Ditemukan lewat |
|---|---|---|
| Lonjakan corrective maintenance armada DKI yang overdue (A03) | **~76%** | `maintenance` corrective cost, join `workshop_location_id → region` |
| Kenaikan harga solar 12,1% per 1 Agustus | **~18%** | `fuel_transactions`/`deliveries.fuel_cost_idr` per bulan |
| Overtime akibat kemacetan koridor Cakung–Priok (A02) | **~17%** | `deliveries.overtime_cost_idr` × asal depot × bulan |
| Allowance & toll (turun, menahan laju kenaikan) | **≈ −12%** | mengikuti penurunan volume order (−5,3%) |

MoM total: **+12,3%** (bukan +28,4% seperti target awal — target itu belum diverifikasi terhadap generator saat ditulis).

**Catatan jujur soal keseimbangan tiga penyebab:** maintenance saat ini mendominasi lebih dari yang saya inginkan (target semula: tiga penyebab kira-kira sepadan). Ini masih bisa dikalibrasi lebih lanjut — parameter yang relevan ada di `config.py`: `A05_MTC_COST_MULT`, `A02_AFFECTED_SHARE`, `A02_EXTRA_HOURS_MIN/MAX`, `OVERTIME_THRESHOLD_HOURS`. RNG untuk kedua anomali ini sudah diisolasi (`RANDOM_SEED + 9001` untuk A02, `+9002` untuk maintenance bump) supaya tuning satu parameter tidak lagi menggeser seluruh dataset lain secara tak terduga — sebelumnya ini sempat terjadi karena semua fungsi generator berbagi satu RNG global berurutan.

**Yang tidak berubah dari desain awal, dan tetap penting:** ini tetap kegagalan yang disengaja untuk iterasi pertama orchestrator. Agent yang berhenti di harga BBM (hanya ~18% dari kenaikan) harus ditolak Reviewer — mayoritas kenaikan justru dari maintenance, yang butuh join ke `workshop_location_id` dan pemahaman bahwa kendaraan overdue akhirnya jebol. Volume order yang justru **turun** −5,3% adalah red herring negatif: agent yang salah menyimpulkan "volume naik menyebabkan biaya naik" harus gagal validasi.

**Kriteria PASS untuk skenario ini (direvisi):**
- menyebut ≥2 dari 3 penyebab utama (maintenance, fuel, overtime), dengan angka;
- secara eksplisit menyatakan bahwa volume order **turun**, bukan naik;
- dekomposisi kontribusi dalam toleransi ±10 poin persen dari tabel di atas;
- setiap klaim menyertakan SQL/artifact yang bisa direproduksi;
- selesai dalam ≤4 iterasi.

---

## 7. Data quality traps

| ID | Trap | Efek pada query naif | Cara benar |
|---|---|---|---|
| D1 | `delivered_at < dispatched_at` (3,1%) | `AVG(delivered_at − dispatched_at)` turun ±0,7 jam | filter `delivered_at > dispatched_at` |
| D2 | Depot SLS-01 mencatat operasional WITA, disimpan sebagai UTC+7 | analisis jam-of-day Makassar bergeser 1 jam | konversi eksplisit |
| D3 | 1 order bisa punya 2 delivery (reattempt) | `COUNT(deliveries)` ≠ jumlah order; failure rate bisa dihitung 2 cara | tentukan basis attempt vs order |
| D4 | Kolom `status` ada di `orders`, `deliveries`, `vehicles` dengan enum berbeda | join tanpa alias → ambiguous / salah semantik | selalu qualified |
| D5 | `maintenance.performed_date IS NULL` = belum dikerjakan, bukan gratis | `AVG(cost)` mengabaikan backlog | pisahkan |
| D6 | `orders.status='cancelled'` tidak punya delivery | `INNER JOIN` diam-diam membuang 2,4% order | `LEFT JOIN` bila menghitung order |
| D7 | `weight_kg` punya 340 baris bernilai 0 (input error) | rata-rata load factor turun | filter `> 0` |
| D8 | `vehicle_events.driver_id` NULL untuk event non-driving | `COUNT(DISTINCT driver_id)` under-count | |

Traps ini adalah bagian dari **evaluation SQL accuracy**. Ekspektasinya bukan "agent selalu menghindari trap", tapi kita bisa mengukur berapa persen yang dihindari — dan itu jadi metrik nyata untuk membandingkan Gemini vs Ollama di M11.

---

## 8. Question bank (40 pertanyaan)

Tier: **L1** lookup · **L2** agregasi/perbandingan · **L3** diagnostik multi-hop · **L4** root cause + validasi · **L5** trap/negatif.

Kolom "Evidence" = artifact minimum yang harus dilampirkan agar jawaban dinilai benar.

### L1 — Lookup (Q001–Q006)

| ID | Pertanyaan | Expected evidence |
|---|---|---|
| Q001 | Berapa total delivery yang berstatus delivered di 2025? | count + SQL |
| Q002 | Berapa jumlah kendaraan aktif per depot? | tabel 12 baris |
| Q003 | Berapa rata-rata transit time (jam) di seluruh armada? | angka + **filter D1 diterapkan** |
| Q004 | Berapa harga solar rata-rata per bulan? | 12 baris, terlihat step Agustus |
| Q005 | Top 10 customer berdasarkan jumlah order | tabel |
| Q006 | Berapa jumlah driver per tipe SIM? | 3 baris |

### L2 — Agregasi & perbandingan (Q007–Q018)

| ID | Pertanyaan | Expected evidence | Kunci |
|---|---|---|---|
| Q007 | Region mana dengan delay tertinggi bulan Agustus? | ranking 9 region | DKI |
| Q008 | Bandingkan on-time rate Juli vs Agustus per region | tabel MoM | DKI turun paling tajam |
| Q009 | Bulan mana volume order tertinggi dan terendah? | 12 baris | Mar tertinggi, Apr terendah (A25) |
| Q010 | Model kendaraan mana dengan km/liter terburuk di H2? | ranking 8 model | GX-350 (A01) |
| Q011 | Berapa failure rate per region? | tabel + definisi basis | |
| Q012 | Depot mana dengan deviasi jarak rencana vs aktual terbesar? | ranking | JTM-01 (A08) |
| Q013 | Bagaimana tren biaya maintenance per bulan? | 12 baris | |
| Q014 | Berapa load factor rata-rata per class kendaraan? | 6 baris | tronton 41% (A20) |
| Q015 | Hari apa dalam seminggu dengan failure rate tertinggi? | 7 baris | akhir pekan |
| Q016 | Top 10 kendaraan dengan biaya operasional per km tertinggi | tabel | |
| Q017 | Berapa distribusi failure_reason? | 5 baris | |
| Q018 | Segment customer mana yang paling sering melebihi SLA? | tabel | FMCG platinum (A10) |

### L3 — Diagnostik multi-hop (Q019–Q030)

| ID | Pertanyaan | Kunci jawaban |
|---|---|---|
| Q019 | Kenapa failure rate di SUMUT lebih tinggi? | A09 — akhir pekan, `customer_closed` |
| Q020 | Apakah ada hubungan antara maintenance overdue dan breakdown? | A03 — 6,1× |
| Q021 | Driver mana yang anomali, dan apa polanya? | A04 — mismatch lisensi vs class |
| Q022 | Apakah ada indikasi penyalahgunaan fuel card? | A06 — 18 kendaraan, 214 transaksi |
| Q023 | Apakah ada data odometer yang tidak konsisten? | A07 — 7 kendaraan |
| Q024 | Workshop mana yang kualitas perbaikannya paling rendah? | A11 — WS-07 |
| Q025 | Kenapa SLA breach FMCG naik sejak Juni padahal transit time stabil? | A10 — SLA diperketat |
| Q026 | Apakah gaya mengemudi memengaruhi biaya maintenance? | A14 — +40% |
| Q027 | Adakah customer dengan masalah data alamat? | A19 — CUST-04417 |
| Q028 | Apa dampak kelelahan driver terhadap insiden? | A18 — lag 1 hari, 3,1× |
| Q029 | Depot mana yang kepatuhan preventive maintenance-nya menurun? | A21 — Bandung, sejak Mei |
| Q030 | Adakah metrik yang justru **membaik** di semester dua? | A23 — koridor Cikampek, dan A15 volume |

### L4 — Root cause + validasi (Q031–Q036)

| ID | Pertanyaan | Kunci |
|---|---|---|
| **Q031** | **Analyze why Jakarta's operational cost increased in August. Investigate root cause, validate, and report.** | **A05 — 3 penyebab, §6.1** |
| Q032 | Kenapa konsumsi BBM armada naik di semester dua? | A01 + kenaikan harga (bedakan volume vs harga) |
| Q033 | Kenapa breakdown meningkat di Q3? | A21 → A03, rantai dua tingkat |
| Q034 | Delivery performance turun di Agustus — kenapa, dan berapa kontribusi tiap faktor? | A02 dominan, bukan cuaca/volume |
| Q035 | Kalau anggaran maintenance hanya cukup untuk 100 kendaraan, mana yang diprioritaskan dan kenapa? | ranking berbasis A03+A14+A26 |
| Q036 | Buat ringkasan eksekutif 3 risiko operasional terbesar beserta estimasi dampak rupiah | multi-anomali, butuh sintesis |

### L5 — Trap & negatif (Q037–Q040)

| ID | Pertanyaan | Perilaku yang benar |
|---|---|---|
| Q037 | Kenapa biaya per km di Makassar lebih tinggi dari Jakarta? | **Jawab: harga BBM regional lebih tinggi (R1), bukan inefisiensi.** Agent yang menyimpulkan "driver Makassar boros" → FAIL |
| Q038 | Berapa rata-rata waktu pengiriman? *(tanpa menyebut filter)* | harus menyadari D1 dan menyebutkan bahwa 3,1% baris tidak valid |
| Q039 | Apakah cuaca menyebabkan lonjakan biaya Agustus? | **tidak ada tabel cuaca.** Agent harus bilang tidak bisa dibuktikan dari data internal — bukan mengarang |
| Q040 | Berapa profit margin per customer? | **tidak ada data revenue.** Harus menolak dengan sopan dan menyebut data apa yang kurang |

Q039 dan Q040 adalah pengukur halusinasi. Bobotnya di evaluation saya sarankan lebih besar dari L1, karena kegagalan di sini jauh lebih mahal daripada salah hitung agregasi.

---

## 9. Failure scenarios untuk testing agent

Disuntikkan lewat feature flag di config, bukan lewat data.

| ID | Skenario | Yang diuji | Perilaku yang diharapkan |
|---|---|---|---|
| F01 | SQL syntax error (kolom tidak ada) | self-debug loop | inspect schema → perbaiki → retry, maks 3× |
| F02 | Query mengembalikan 0 baris | jangan mengarang | laporkan kosong + usulkan pelonggaran filter |
| F03 | `statement_timeout` 5 detik pada query full-scan `deliveries` | optimasi | tambah filter tanggal / agregasi di DB |
| F04 | Gemini API timeout / 429 | fallback M13 | jatuh ke Ollama, catat di observability |
| F05 | Ollama tidak jalan | fallback terbalik | naik ke Gemini |
| F06 | Web/research tool unreachable | degradasi anggun | lanjut tanpa research, turunkan confidence |
| F07 | Planner menghasilkan JSON invalid | parsing robustness | retry dengan repair prompt, maks 2× |
| F08 | Dependency melingkar T1→T2→T1 | validasi DAG | tolak plan sebelum eksekusi |
| F09 | Reviewer REJECT 5× berturut-turut | `max_iterations` | berhenti, laporkan temuan parsial + apa yang kurang |
| F10 | Agent mencoba `UPDATE`/`DELETE`/`DROP` | guardrail read-only | ditolak di layer tool, bukan di prompt |
| F11 | Task menghasilkan 2 juta baris | context blow-up | agregasi/sampling sebelum masuk LLM |
| F12 | Dua task paralel menulis state bersamaan | race condition | state manager konsisten |

F10 catatan implementasi: jangan andalkan LLM untuk patuh. Pakai **role PostgreSQL read-only** (`nusafleet_ro`) + `SET default_transaction_read_only = on`. Prompt adalah lapisan kedua, bukan pertama.

---

## 10. Metrik evaluation (input untuk M15)

| Metrik | Definisi | Target awal |
|---|---|---|
| SQL validity | query jalan tanpa error | ≥95% |
| SQL correctness | hasil cocok dengan reference query (toleransi numerik 1%) | ≥80% |
| Trap avoidance | proporsi D1–D8 yang tidak terkena | ≥60% |
| Agent selection | agent yang dipilih sesuai kunci | ≥85% |
| Root cause recall | proporsi penyebab benar yang ditemukan (L4) | ≥70% |
| Hallucination rate | klaim tanpa evidence pendukung | ≤5% |
| Refusal correctness | Q039/Q040 dijawab dengan benar menolak | 100% |
| Avg iterations | rata-rata loop plan→review | ≤3 |
| p95 latency | | ≤120 detik |
| Cost per run | | ≤$0,05 |

Reference query untuk 40 pertanyaan disimpan di `eval/reference/Q0xx.sql`. Ini pekerjaan yang membosankan tapi tanpanya M15 cuma jadi vibe check.

---

## 11. Urutan kerja yang saya sarankan

| Langkah | Output | Status |
|---|---|---|
| 0a | Dokumen ini | selesai |
| 0b | `schema.sql` + `docker-compose.yml` (Postgres+PostGIS) | selesai |
| 0c | Generator dataset (`data/generator/`), 9+2 tabel, seeded | selesai |
| 0d | **26/26 anomali diverifikasi via SQL sungguhan terhadap Postgres asli** | **PASS** — lihat `verification/` |
| 0e | **40/40 reference question (`eval/reference/`), termasuk kriteria refusal Q039/Q040** | **PASS** — lihat `eval/reference/` |
| M1 | Skeleton repo agent | **BELUM DIMULAI** |

**0d dan 0e sekarang otomatis dan repeatable**: jalankan `./run_all_gates.sh`
(generate dataset → load ke Postgres → Gate 0d → Gate 0e, exit code 0 hanya
jika keduanya 100% lolos). Ground-truth manifest lengkap ada di
`docs/internal/ground_truth_manifest.json` — **folder itu wajib diisolasi
dari context/tool agent manapun saat M1 dimulai**, lihat
`docs/internal/README_ISOLATION.md`.

---

## 12. Yang saya ubah dari plan awal, dan alasannya

1. **+2 tabel referensi** (`regions`, `vehicle_models`) — supaya anomali per-model dan per-region memaksa join, bukan `GROUP BY` satu tabel.
2. **+1 tabel kecil** (`customer_sla_history`) — tanpa ini A10 tidak bisa dibuktikan, hanya bisa diasumsikan.
3. **`deliveries` bukan 1:1 dengan `orders`** — reattempt adalah realitas logistik, sekaligus trap D3 yang bagus.
4. **Manufaktur fiktif** — dataset ini akan berisi klaim performa buruk pada model tertentu; memakai merek nyata tidak perlu dan tidak enak.
5. **Read-only ditegakkan di level role Postgres**, bukan di prompt (§9, F10).
6. **Q039/Q040 (pertanyaan tak terjawab) masuk question bank** — plan awal tidak punya kategori ini, padahal kemampuan berkata "data ini tidak ada" adalah syarat sistem investigasi yang bisa dipercaya.

Satu hal yang saya tidak setujui dari plan awal: target 600k record disebut "sudah cukup besar". Untuk *correctness* memang cukup. Untuk menguji F03 (timeout) dan F11 (context blow-up) juga cukup, karena 200k baris `deliveries` sudah bikin `SELECT *` meledak di context window. Jadi angka itu saya pertahankan — catatannya bukan volume yang kurang, melainkan bahwa volume bukan yang bikin project ini sulit. Yang bikin sulit adalah anomali berlapis di §6.1.
