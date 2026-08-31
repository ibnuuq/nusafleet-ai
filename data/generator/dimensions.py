"""Generate tabel dimensi (referensi & master)."""
import numpy as np
import pandas as pd
from faker import Faker

import config as cfg

fake = Faker("id_ID")
Faker.seed(cfg.RANDOM_SEED)


def gen_regions():
    rows = []
    for rid, code, name, island, lat, lon, cong in cfg.REGIONS:
        rows.append(dict(region_id=rid, region_code=code, region_name=name,
                          island=island, lat=lat, lon=lon, congestion_index=cong))
    return pd.DataFrame(rows)


def _jitter_point(lat, lon, radius_km):
    # sebaran kasar normal di sekitar centroid, cukup untuk sintetis (bukan GIS presisi)
    deg = radius_km / 111.0
    dlat = cfg.RNG.normal(0, deg / 2)
    dlon = cfg.RNG.normal(0, deg / 2)
    return lat + dlat, lon + dlon


def gen_locations(regions_df):
    rows = []
    loc_id = 1

    # 12 depot (koordinat eksplisit dari config, bukan random)
    depot_ids = {}
    for code, name, region_code, lat, lon in cfg.DEPOTS:
        region_id = int(regions_df.loc[regions_df.region_code == region_code, "region_id"].iloc[0])
        rows.append(dict(location_id=loc_id, location_code=code, name=name,
                          loc_type="depot", region_id=region_id,
                          address=f"{name}, {region_code}", lat=lat, lon=lon))
        depot_ids[code] = loc_id
        loc_id += 1

    region_weights = np.array([cfg.REGION_ORDER_SHARE[c] for c in regions_df.region_code])
    region_weights = region_weights / region_weights.sum()

    def add_batch(n, loc_type, prefix, radius_km):
        nonlocal loc_id
        region_choice = cfg.RNG.choice(regions_df.region_id.values, size=n, p=region_weights)
        for i in range(n):
            rid = int(region_choice[i])
            rrow = regions_df.loc[regions_df.region_id == rid].iloc[0]
            lat, lon = _jitter_point(rrow.lat, rrow.lon, radius_km)
            rows.append(dict(
                location_id=loc_id,
                location_code=f"{prefix}-{loc_id:06d}",
                name=f"{loc_type.replace('_', ' ').title()} {loc_id}",
                loc_type=loc_type, region_id=rid,
                address=fake.address().replace("\n", ", "),
                lat=lat, lon=lon))
            loc_id += 1

    add_batch(18, "workshop", "WS", 30)
    add_batch(220, "fuel_station", "FS", 35)
    add_batch(50, "rest_area", "RA", 40)
    add_batch(4700, "customer_site", "CS", 45)

    df = pd.DataFrame(rows)
    return df, depot_ids


def gen_vehicle_models():
    rows = []
    for i, (code, mfr, name, vclass, cap, kpl, year) in enumerate(cfg.VEHICLE_MODELS, start=1):
        rows.append(dict(model_id=i, model_code=code, manufacturer=mfr, model_name=name,
                          v_class=vclass, capacity_kg=cap, fuel_type="diesel",
                          nominal_km_per_liter=kpl, year_introduced=year))
    return pd.DataFrame(rows)


def gen_vehicles(vehicle_models_df, locations_df, depot_ids):
    n = cfg.N_VEHICLES
    model_codes = list(cfg.MODEL_SHARE.keys())
    model_p = np.array([cfg.MODEL_SHARE[c] for c in model_codes])
    chosen_models = cfg.RNG.choice(model_codes, size=n, p=model_p)

    model_lookup = vehicle_models_df.set_index("model_code")
    depot_codes = list(depot_ids.keys())

    year_start = pd.Timestamp("2016-01-01")
    year_end = pd.Timestamp("2025-03-01")
    span_days = (year_end - year_start).days

    rows = []
    for i in range(n):
        mcode = chosen_models[i]
        mrow = model_lookup.loc[mcode]
        model_id = int(mrow.model_id)
        vclass = mrow.v_class

        # skew akuisisi ke tahun2 belakangan
        u = cfg.RNG.beta(2.2, 1.3)
        acq_date = year_start + pd.Timedelta(days=int(u * span_days))
        age_years = (pd.Timestamp("2025-12-31") - acq_date).days / 365.25

        odometer = max(500, int(age_years * 62000 * cfg.RNG.normal(1.0, 0.18)))
        depot_code = depot_codes[cfg.RNG.integers(0, len(depot_codes))]

        interval = cfg.SERVICE_INTERVAL_BY_CLASS[vclass]
        # sebagian sengaja overdue untuk A03: last_service jauh di belakang
        overdue_flag = cfg.RNG.random() < 0.12
        if overdue_flag:
            last_service = max(0, odometer - int(interval * cfg.RNG.uniform(1.3, 2.2)))
        else:
            last_service = max(0, odometer - int(interval * cfg.RNG.uniform(0.1, 0.95)))

        status_roll = cfg.RNG.random()
        status = "retired" if status_roll < 0.03 else ("in_maintenance" if status_roll < 0.12 else "active")

        rows.append(dict(
            vehicle_id=i + 1,
            # index disertakan supaya dijamin unik (sebelumnya murni random -> bisa collide,
            # tertangkap oleh UNIQUE constraint saat load ke Postgres)
            plate_number=f"{depot_code[:1]}{1000+i:04d}{fake.random_uppercase_letter()}{fake.random_uppercase_letter()}",
            model_id=model_id,
            home_depot_id=depot_ids[depot_code],
            acquisition_date=acq_date.date(),
            odometer_km=odometer,
            status=status,
            service_interval_km=interval,
            last_service_odometer_km=last_service,
            tank_capacity_liter=cfg.TANK_CAPACITY_BY_CLASS[vclass],
            model_code=mcode,
            depot_code=depot_code,
        ))
    return pd.DataFrame(rows)


def gen_drivers(locations_df, depot_ids):
    n = cfg.N_DRIVERS
    depot_codes = list(depot_ids.keys())
    lic_codes = list(cfg.LICENSE_SHARE.keys())
    lic_p = np.array([cfg.LICENSE_SHARE[c] for c in lic_codes])
    emp_codes = list(cfg.EMPLOYMENT_SHARE.keys())
    emp_p = np.array([cfg.EMPLOYMENT_SHARE[c] for c in emp_codes])

    year_start = pd.Timestamp("2015-01-01")
    year_end = pd.Timestamp("2025-09-01")
    span_days = (year_end - year_start).days

    rows = []
    for i in range(n):
        depot_code = depot_codes[cfg.RNG.integers(0, len(depot_codes))]
        hire_date = year_start + pd.Timedelta(days=int(cfg.RNG.uniform(0, span_days)))
        rows.append(dict(
            driver_id=i + 1,
            driver_code=f"DRV-{i+1:04d}",
            full_name=fake.name(),
            license_type=cfg.RNG.choice(lic_codes, p=lic_p),
            hire_date=hire_date.date(),
            home_depot_id=depot_ids[depot_code],
            employment_status=cfg.RNG.choice(emp_codes, p=emp_p),
            birth_year=int(cfg.RNG.integers(1970, 2005)),
            safety_score=round(float(np.clip(cfg.RNG.normal(78, 11), 20, 99)), 1),
        ))
    return pd.DataFrame(rows)


def gen_customers(regions_df, locations_df):
    n = cfg.N_CUSTOMERS
    region_weights = np.array([cfg.REGION_ORDER_SHARE[c] for c in regions_df.region_code])
    region_weights = region_weights / region_weights.sum()

    seg_codes = list(cfg.CUSTOMER_SEGMENT_SHARE.keys())
    seg_p = np.array([cfg.CUSTOMER_SEGMENT_SHARE[c] for c in seg_codes])
    tier_codes = list(cfg.CUSTOMER_TIER_SHARE.keys())
    tier_p = np.array([cfg.CUSTOMER_TIER_SHARE[c] for c in tier_codes])

    cust_sites = locations_df[locations_df.loc_type == "customer_site"].reset_index(drop=True)
    cust_sites_by_region = {rid: g.location_id.values for rid, g in cust_sites.groupby("region_id")}

    year_start = pd.Timestamp("2019-01-01")
    year_end = pd.Timestamp("2025-10-01")
    span_days = (year_end - year_start).days

    rows = []
    sla_history_rows = []
    for i in range(n):
        rid = int(cfg.RNG.choice(regions_df.region_id.values, p=region_weights))
        seg = cfg.RNG.choice(seg_codes, p=seg_p)
        tier = cfg.RNG.choice(tier_codes, p=tier_p)
        sites = cust_sites_by_region.get(rid)
        primary_loc = int(cfg.RNG.choice(sites)) if sites is not None and len(sites) else None
        contract_start = year_start + pd.Timedelta(days=int(cfg.RNG.uniform(0, span_days)))

        # A10: platinum FMCG SLA diperketat 36 -> 24 sejak 2025-06-01
        is_a10 = (tier == "platinum" and seg == "fmcg")
        sla_now = cfg.SLA_HOURS_BY_TIER[tier]
        customer_id = i + 1

        rows.append(dict(
            customer_id=customer_id,
            customer_code=f"CUST-{customer_id:05d}",
            company_name=fake.company(),
            segment=seg, tier=tier, region_id=rid,
            primary_location_id=primary_loc,
            contract_start_date=contract_start.date(),
            sla_hours=sla_now,
            is_active=bool(cfg.RNG.random() < 0.94),
        ))

        if is_a10:
            sla_history_rows.append(dict(customer_id=customer_id, effective_from="2019-01-01", sla_hours=36))
            sla_history_rows.append(dict(customer_id=customer_id, effective_from="2025-06-01", sla_hours=24))
        else:
            sla_history_rows.append(dict(customer_id=customer_id, effective_from="2019-01-01", sla_hours=sla_now))

    return pd.DataFrame(rows), pd.DataFrame(sla_history_rows)
