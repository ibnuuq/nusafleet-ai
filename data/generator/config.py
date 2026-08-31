"""
Konstanta & konfigurasi generator NusaFleet.
Semua angka di sini mengikuti docs/internal/design_dataset_and_scenarios.md
— jangan ubah salah satu tanpa mengubah yang lain, karena anomali saling
bergantung (mis. fuel price step vs A05 decomposition).
"""
import numpy as np

RANDOM_SEED = 20250101
RNG = np.random.default_rng(RANDOM_SEED)

YEAR_START = "2025-01-01"
YEAR_END = "2025-12-31"

# ---------------------------------------------------------------- regions
REGIONS = [
    # id, code, name, island, lat, lon, congestion_index
    (1, "DKI",    "DKI Jakarta",     "Jawa",      -6.20, 106.85, 1.35),
    (2, "JABAR",  "Jawa Barat",      "Jawa",      -6.91, 107.61, 1.15),
    (3, "BANTEN", "Banten",          "Jawa",      -6.22, 106.63, 1.10),
    (4, "JATENG", "Jawa Tengah",     "Jawa",      -6.97, 110.42, 1.00),
    (5, "JATIM",  "Jawa Timur",      "Jawa",      -7.25, 112.75, 1.05),
    (6, "SUMUT",  "Sumatera Utara",  "Sumatera",  3.59,   98.67, 0.95),
    (7, "SUMSEL", "Sumatera Selatan","Sumatera", -2.98,  104.76, 0.90),
    (8, "SULSEL", "Sulawesi Selatan","Sulawesi", -5.14,  119.42, 0.88),
    (9, "BALI",   "Bali",            "Bali",     -8.65,  115.22, 0.92),
]
REGION_ORDER_SHARE = {  # share dari total 200k order (§5.1)
    "DKI": 0.24, "JABAR": 0.18, "JATIM": 0.15, "JATENG": 0.11,
    "BANTEN": 0.10, "SUMUT": 0.08, "SUMSEL": 0.05, "SULSEL": 0.05, "BALI": 0.04,
}

MONTHLY_MULTIPLIER = {  # §5.1
    1: 0.92, 2: 0.89, 3: 1.48, 4: 0.71, 5: 0.97, 6: 1.03,
    7: 1.05, 8: 1.04, 9: 1.12, 10: 1.18, 11: 1.26, 12: 1.35,
}
DOW_MULTIPLIER = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 0.55, 6: 0.18}  # Mon=0

DEPOTS = [  # code, name, region_code, lat, lon
    ("JKT-01", "Depot Cakung",       "DKI",   -6.174, 106.945),
    ("JKT-02", "Depot Tanjung Priok","DKI",   -6.104, 106.880),
    ("JKT-03", "Depot Cengkareng",   "DKI",   -6.129, 106.716),
    ("BTN-01", "Depot Balaraja",     "BANTEN",-6.173, 106.352),
    ("JBR-01", "Depot Bandung",      "JABAR", -6.917, 107.619),
    ("JBR-02", "Depot Cikarang",     "JABAR", -6.301, 107.155),
    ("JTG-01", "Depot Semarang",     "JATENG",-6.966, 110.417),
    ("JTM-01", "Depot Surabaya",     "JATIM", -7.250, 112.750),
    ("JTM-02", "Depot Malang",       "JATIM", -7.983, 112.621),
    ("SMU-01", "Depot Medan",        "SUMUT",  3.595,  98.672),
    ("SLS-01", "Depot Makassar",     "SULSEL",-5.147, 119.432),
    ("BLI-01", "Depot Denpasar",     "BALI",  -8.650, 115.216),
]

VEHICLE_MODELS = [
    # code, manufacturer, name, class, capacity_kg, km_per_liter, year
    ("GX-200", "Garuda Motors",    "GX-200", "cdd",          4000,  9.2, 2018),
    ("GX-350", "Garuda Motors",    "GX-350", "cde",          8000,  8.4, 2017),
    ("ST-90",  "Sentosa Trucks",   "ST-90",  "van",          1200, 12.5, 2019),
    ("ST-450", "Sentosa Trucks",   "ST-450", "tronton",     16000,  5.6, 2016),
    ("RB-120", "Rimba Auto",       "RB-120", "wingbox",      7500,  7.8, 2018),
    ("RB-600", "Rimba Auto",       "RB-600", "tractor_head",24000,  4.2, 2017),
    ("NV-75",  "Nusantara Niaga",  "NV-75",  "van",          1000, 13.1, 2020),
    ("NT-300", "Nusantara Niaga",  "NT-300", "cde",          8000,  8.6, 2019),
]
MODEL_SHARE = {  # §4.5
    "GX-350": 0.22, "NT-300": 0.18, "RB-120": 0.15, "GX-200": 0.14,
    "ST-450": 0.12, "NV-75": 0.08, "ST-90": 0.07, "RB-600": 0.04,
}
SERVICE_INTERVAL_BY_CLASS = {
    "van": 10000, "cdd": 15000, "cde": 15000,
    "wingbox": 20000, "tronton": 20000, "tractor_head": 25000,
}
TANK_CAPACITY_BY_CLASS = {
    "van": 60, "cdd": 100, "cde": 150, "wingbox": 150,
    "tronton": 200, "tractor_head": 400,
}

# ---------------------------------------------------------------- fuel price (§5.3)
def fuel_price_for(date):
    m = date.month
    if m <= 3:
        base = 14200
    elif m <= 6:
        base = 14650
    elif m == 7:
        base = 14900
    else:
        base = 16700   # step 1 Agustus -> penyebab utama A05
    return base

FUEL_REGIONAL_FACTOR = {  # red herring R1 (§5.3)
    "SULSEL": 1.06, "SUMUT": 1.04, "SUMSEL": 1.03, "BALI": 1.05,
}

CUSTOMER_SEGMENT_SHARE = {"fmcg": 0.30, "manufacturing": 0.25, "ecommerce": 0.20, "retail": 0.18, "pharma": 0.07}
CUSTOMER_TIER_SHARE = {"bronze": 0.45, "silver": 0.30, "gold": 0.20, "platinum": 0.05}
SLA_HOURS_BY_TIER = {"bronze": 72, "silver": 48, "gold": 36, "platinum": 24}
SLA_HOURS_BY_TIER_BEFORE_JUNE = {"bronze": 72, "silver": 48, "gold": 36, "platinum": 36}  # A10: platinum was 36 before

LICENSE_SHARE = {"B1": 0.20, "B2": 0.45, "B2_UMUM": 0.35}
EMPLOYMENT_SHARE = {"permanent": 0.62, "contract": 0.33, "resigned": 0.05}

N_CUSTOMERS = 10_000
N_DRIVERS = 2_000
N_VEHICLES = 1_000
N_LOCATIONS = 5_000
N_ORDERS = 200_000
N_FUEL_TX = 100_000
N_MAINTENANCE = 20_000
N_VEHICLE_EVENTS = 100_000

# Anomali A01: unit GX-350 tua yang mulai degradasi efisiensi sejak Mei 2025
A01_MODEL = "GX-350"
A01_ACQ_BEFORE = "2023-01-01"
A01_START_MONTH = 5           # Mei
A01_EFFICIENCY_DROP = 0.167   # 8.4 -> ~7.0 km/l

# Anomali A02: koridor Cakung <-> Tanjung Priok macet mulai Agustus.
# Diterapkan sebagai delay ADITIF (bukan pengali) pada delivery yang BERANGKAT
# dari salah satu depot ini -- karena base transit intra-kota sudah pendek
# (median ~2-3 jam), pengali kecil tidak akan pernah mendorongnya melewati
# ambang overtime. Delay aditif mensimulasikan waktu terjebak macet.
A02_ORIGIN_DEPOTS = ("JKT-01", "JKT-02")
A02_START_MONTH = 8
A02_AFFECTED_SHARE = 0.42   # hanya sebagian rute yang benar2 lewat titik macet
A02_EXTRA_HOURS_MIN = 1.8
A02_EXTRA_HOURS_MAX = 3.6

# Ambang overtime driver (jam). 9 jam terlalu tinggi untuk rute last-mile
# intra-kota yang basisnya cuma 1-3 jam -- diturunkan supaya delay macet
# di atas benar-benar memicu biaya overtime.
OVERTIME_THRESHOLD_HOURS = 5.0
OVERTIME_RATE_IDR = 40000

# Anomali A06: fuel card fraud pada ~18 kendaraan
A06_N_VEHICLES = 18

# Anomali A07: odometer rollback pada 7 kendaraan
A07_N_VEHICLES = 7

# Anomali A09: failure rate SUMUT akhir pekan lebih tinggi
A09_REGION = "SUMUT"
A09_WEEKEND_FAILURE_MULT = 2.5

# Anomali A03/A21: kepatuhan preventive maintenance Bandung turun sejak Mei
A21_WORKSHOP_REGION = "JABAR"
A21_START_MONTH = 5
A21_COMPLIANCE_BEFORE = 0.88
A21_COMPLIANCE_AFTER = 0.61

# A05 (skenario Definition of Done): kendaraan DKI yang overdue service akhirnya
# jebol pada Agustus -> lonjakan corrective maintenance cost DKI di bulan itu.
A05_MTC_REGION = "DKI"
A05_MTC_BUMP_MONTH = 8
A05_MTC_BUMP_SHARE = 0.50
A05_MTC_COST_MULT = 2.6

# Data quality traps
D1_BAD_TIMESTAMP_SHARE = 0.031   # delivered_at < dispatched_at (bug SMU-01)
D7_ZERO_WEIGHT_ROWS = 340
