"""Generate tabel fakta. Vektorisasi numpy dipakai di bagian volume besar
(orders, deliveries) supaya generator tetap jalan dalam hitungan menit."""
import numpy as np
import pandas as pd

import config as cfg


# --------------------------------------------------------------------- orders
def gen_orders(customers_df, locations_df, depot_ids):
    days = pd.date_range(cfg.YEAR_START, cfg.YEAR_END, freq="D")
    day_weight = np.array([
        cfg.MONTHLY_MULTIPLIER[d.month] * cfg.DOW_MULTIPLIER[d.dayofweek] for d in days
    ])
    # A15: lonjakan tanggal kembar untuk segment ecommerce (ditangani lewat boost harian umum
    # + boost tambahan khusus ecommerce saat assignment customer di bawah)
    twin_dates = {f"2025-{m:02d}-{m:02d}" for m in range(9, 13)}  # 9/9 10/10 11/11 12/12
    twin_mask = np.array([str(d.date()) in twin_dates for d in days])
    day_weight = day_weight * np.where(twin_mask, 1.8, 1.0)

    day_weight = day_weight / day_weight.sum()
    n = cfg.N_ORDERS
    day_idx = cfg.RNG.choice(len(days), size=n, p=day_weight)
    order_days = days[day_idx]

    # jam pickup bimodal: puncak 06-09 dan 19-22
    comp = cfg.RNG.random(n) < 0.55
    hour = np.where(
        comp,
        np.clip(cfg.RNG.normal(7.5, 1.1, n), 0, 23.9),
        np.clip(cfg.RNG.normal(20.5, 1.3, n), 0, 23.9),
    )
    order_date = order_days + pd.to_timedelta(hour, unit="h")

    region_codes = list(cfg.REGION_ORDER_SHARE.keys())
    region_p = np.array([cfg.REGION_ORDER_SHARE[c] for c in region_codes])
    region_p = region_p / region_p.sum()

    cust_by_region = {code: g.customer_id.values for code, g in
                       customers_df.merge(
                           pd.DataFrame(cfg.REGIONS, columns=["region_id","region_code","region_name","island","lat","lon","cong"])[["region_id","region_code"]],
                           on="region_id").groupby("region_code")}

    depot_by_region_code = {}
    for code, name, region_code, lat, lon in cfg.DEPOTS:
        depot_by_region_code.setdefault(region_code, []).append(depot_ids[code])

    cust_sites = locations_df[locations_df.loc_type == "customer_site"]
    sites_by_region_id = {rid: g.location_id.values for rid, g in cust_sites.groupby("region_id")}
    region_code_to_id = {c: rid for rid, c, *_ in cfg.REGIONS}

    chosen_region = cfg.RNG.choice(region_codes, size=n, p=region_p)

    customer_ids = np.empty(n, dtype=np.int64)
    origin_loc = np.empty(n, dtype=np.int64)
    dest_loc = np.empty(n, dtype=np.int64)
    for code in region_codes:
        mask = chosen_region == code
        cnt = mask.sum()
        if cnt == 0:
            continue
        pool = cust_by_region.get(code)
        customer_ids[mask] = cfg.RNG.choice(pool, size=cnt)
        depots = depot_by_region_code.get(code, list(depot_ids.values()))
        origin_loc[mask] = cfg.RNG.choice(depots, size=cnt)
        rid = region_code_to_id[code]
        dest_pool = sites_by_region_id.get(rid)
        dest_loc[mask] = cfg.RNG.choice(dest_pool, size=cnt)

    weight_kg = cfg.RNG.lognormal(mean=np.log(2100), sigma=0.85, size=n)
    weight_kg = np.clip(weight_kg, 5, 30000)
    zero_idx = cfg.RNG.choice(n, size=cfg.D7_ZERO_WEIGHT_ROWS, replace=False)  # [TRAP D7]
    weight_kg[zero_idx] = 0.0
    volume_m3 = weight_kg / cfg.RNG.uniform(180, 260, n)

    priority = cfg.RNG.choice(["standard", "express", "critical"], size=n, p=[0.72, 0.23, 0.05])
    status = cfg.RNG.choice(
        ["delivered", "failed", "cancelled", "in_transit"], size=n, p=[0.912, 0.041, 0.024, 0.023]
    )

    pickup_delay_h = cfg.RNG.uniform(4, 36, n)
    requested_pickup_at = order_date + pd.to_timedelta(pickup_delay_h, unit="h")

    cust_sla = customers_df.set_index("customer_id")["sla_hours"]
    sla_hours = cust_sla.loc[customer_ids].values
    promised_delivery_at = requested_pickup_at + pd.to_timedelta(sla_hours, unit="h")

    order_id = np.arange(1, n + 1)
    df = pd.DataFrame({
        "order_id": order_id,
        "order_code": [f"ORD-2025-{i:06d}" for i in order_id],
        "customer_id": customer_ids,
        "order_date": order_date,
        "requested_pickup_at": requested_pickup_at,
        "promised_delivery_at": promised_delivery_at,
        "origin_location_id": origin_loc,
        "destination_location_id": dest_loc,
        "weight_kg": np.round(weight_kg, 2),
        "volume_m3": np.round(volume_m3, 2),
        "declared_value_idr": (weight_kg * cfg.RNG.uniform(15000, 120000, n)).astype(np.int64),
        "priority": priority,
        "status": status,
        "region_code": chosen_region,
    })
    return df


# ------------------------------------------------------------------ deliveries
def gen_deliveries(orders_df, vehicles_df, drivers_df, locations_df, depot_by_id, regions_df):
    deliverable = orders_df[orders_df.status != "cancelled"].copy()  # [TRAP D6 handled: cancelled has no delivery]

    loc_lookup = locations_df.set_index("location_id")
    reg_lookup = regions_df.set_index("region_id")

    n = len(deliverable)
    veh_active = vehicles_df[vehicles_df.status != "retired"].reset_index(drop=True)
    veh_by_depot = {d: g for d, g in veh_active.groupby("home_depot_id")}
    drv_by_depot = {d: g for d, g in drivers_df[drivers_df.employment_status != "resigned"].groupby("home_depot_id")}

    origin_ids = deliverable.origin_location_id.values
    dest_ids = deliverable.destination_location_id.values
    dest_region_id = loc_lookup.loc[dest_ids, "region_id"].values
    dest_lat = loc_lookup.loc[dest_ids, "lat"].values
    dest_lon = loc_lookup.loc[dest_ids, "lon"].values
    origin_lat = loc_lookup.loc[origin_ids, "lat"].values
    origin_lon = loc_lookup.loc[origin_ids, "lon"].values

    # jarak kasar (haversine sederhana)
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371.0
        p1, p2 = np.radians(lat1), np.radians(lat2)
        dphi = np.radians(lat2 - lat1)
        dlmb = np.radians(lon2 - lon1)
        a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
        return 2 * R * np.arcsin(np.sqrt(a))

    planned_distance = np.clip(haversine(origin_lat, origin_lon, dest_lat, dest_lon) * 1.28, 3, 1400)

    # A08: Depot JTM-01 (Surabaya) under-estimate jarak sistematis
    origin_codes = loc_lookup.loc[origin_ids, "location_code"].values
    a08_mask = origin_codes == "JTM-01"

    vehicle_id = np.empty(n, dtype=np.int64)
    driver_id = np.empty(n, dtype=np.int64)
    for oid, grp_idx in deliverable.groupby("origin_location_id").groups.items():
        idxs = deliverable.index.get_indexer(grp_idx)
        vpool = veh_by_depot.get(oid, veh_active)
        dpool = drv_by_depot.get(oid, drivers_df)
        vehicle_id[idxs] = cfg.RNG.choice(vpool.vehicle_id.values, size=len(idxs))
        driver_id[idxs] = cfg.RNG.choice(dpool.driver_id.values, size=len(idxs))

    veh_lookup = vehicles_df.set_index("vehicle_id")
    model_code = veh_lookup.loc[vehicle_id, "model_code"].values
    acq_date = pd.to_datetime(veh_lookup.loc[vehicle_id, "acquisition_date"].values)

    dispatched_at = pd.to_datetime(deliverable.requested_pickup_at.values) + \
        pd.to_timedelta(cfg.RNG.uniform(-2, 4, n), unit="h")
    month = dispatched_at.month
    hour = dispatched_at.hour

    congestion = reg_lookup.loc[dest_region_id, "congestion_index"].values.astype(float)
    tod_factor = np.where(((hour >= 6) & (hour <= 9)) | ((hour >= 16) & (hour <= 19)), 1.25,
                           np.where((hour >= 22) | (hour <= 4), 0.88, 1.0))
    noise = cfg.RNG.lognormal(0, 0.22, n)
    dwell = cfg.RNG.uniform(0.4, 1.8, n)

    base_hours = planned_distance / 45.0

    # A02: koridor Cakung <-> Tanjung Priok macet mulai Agustus.
    # Berlaku untuk delivery yang BERANGKAT dari salah satu depot itu (bukan
    # mensyaratkan tujuan juga depot -- tujuan selalu customer_site).
    # Delay ADITIF karena base transit intra-kota terlalu pendek untuk
    # pengali kecil bisa mendorongnya melewati ambang overtime.
    # RNG terisolasi (seed tetap, terpisah dari cfg.RNG) supaya menuning
    # A02_* di config.py tidak menggeser aliran acak downstream lainnya.
    a02_rng = np.random.default_rng(cfg.RANDOM_SEED + 9001)
    dest_codes = loc_lookup.loc[dest_ids, "location_code"].values
    a02_eligible = np.isin(origin_codes, list(cfg.A02_ORIGIN_DEPOTS)) & (month >= cfg.A02_START_MONTH)
    a02_mask = a02_eligible & (a02_rng.random(n) < cfg.A02_AFFECTED_SHARE)
    a02_extra_hours = np.where(a02_mask, a02_rng.uniform(cfg.A02_EXTRA_HOURS_MIN, cfg.A02_EXTRA_HOURS_MAX, n), 0.0)

    # A23: tol baru Cikampek-Palimanan sejak 1 Sep -> transit -14% untuk region JABAR
    a23_mask = (reg_lookup.loc[dest_region_id, "region_code"].values == "JABAR") & (month >= 9)
    a23_factor = np.where(a23_mask, 0.86, 1.0)

    transit_hours = base_hours * congestion * tod_factor * noise * a23_factor + dwell + a02_extra_hours

    # A01: GX-350 tua terdegradasi efisiensi mulai Mei -> tidak memengaruhi transit,
    # tapi memengaruhi konsumsi BBM (dipakai di bawah untuk fuel_cost)
    is_a01 = (model_code == cfg.A01_MODEL) & (acq_date < pd.Timestamp(cfg.A01_ACQ_BEFORE)) & (month >= cfg.A01_START_MONTH)

    arrived_at = dispatched_at + pd.to_timedelta(transit_hours, unit="h")

    # status & failure
    status_roll = cfg.RNG.random(n)
    is_weekend = dispatched_at.dayofweek >= 5
    is_sumut = reg_lookup.loc[dest_region_id, "region_code"].values == cfg.A09_REGION
    base_fail_p = 0.041
    fail_p = np.where(is_sumut & is_weekend, base_fail_p * cfg.A09_WEEKEND_FAILURE_MULT, base_fail_p)
    status = np.where(status_roll < fail_p, "failed",
              np.where(status_roll < fail_p + 0.010, "returned", "delivered"))

    failure_reason = np.array([None] * n, dtype=object)
    fail_mask = np.isin(status, ["failed", "returned"])
    reasons = cfg.RNG.choice(
        ["customer_closed", "address_not_found", "refused", "vehicle_breakdown", "document_issue"],
        size=fail_mask.sum(), p=[0.38, 0.22, 0.18, 0.14, 0.08])
    failure_reason[fail_mask] = reasons

    delivered_at = np.where(status == "delivered", arrived_at + pd.to_timedelta(cfg.RNG.uniform(0.05, 0.6, n), unit="h"), pd.NaT)
    delivered_at = pd.to_datetime(pd.Series(delivered_at))

    # [TRAP D1] 3.1% delivered_at < dispatched_at (bug sinkronisasi jam SMU-01)
    smu_mask = (origin_codes == "SMU-01")
    d1_candidates = np.where(smu_mask & (status == "delivered"))[0]
    if len(d1_candidates):
        d1_n = int(len(deliverable) * cfg.D1_BAD_TIMESTAMP_SHARE)
        d1_n = min(d1_n, len(d1_candidates))
        d1_idx = cfg.RNG.choice(d1_candidates, size=d1_n, replace=False)
        bad_delta = pd.to_timedelta(cfg.RNG.uniform(0.1, 2.0, d1_n), unit="h")
        delivered_at_vals = delivered_at.values.copy()
        delivered_at_vals[d1_idx] = (dispatched_at[d1_idx] - bad_delta).values
        delivered_at = pd.Series(delivered_at_vals)

    actual_distance = planned_distance * cfg.RNG.uniform(0.97, 1.10, n)
    actual_distance = np.where(a08_mask, planned_distance * cfg.RNG.uniform(1.15, 1.30, n), actual_distance)  # A08

    price_per_liter = np.array([cfg.fuel_price_for(pd.Timestamp(d)) for d in dispatched_at])
    reg_code_arr = reg_lookup.loc[dest_region_id, "region_code"].values
    regional_factor = np.array([cfg.FUEL_REGIONAL_FACTOR.get(c, 1.0) for c in reg_code_arr])
    price_per_liter = price_per_liter * regional_factor

    kpl_lookup = {m[0]: m[5] for m in cfg.VEHICLE_MODELS}
    nominal_kpl = np.array([kpl_lookup[m] for m in model_code])
    kpl = nominal_kpl * np.where(is_a01, 1 - cfg.A01_EFFICIENCY_DROP, 1.0) * cfg.RNG.normal(1.0, 0.06, n)
    kpl = np.clip(kpl, 2.0, 20.0)

    fuel_cost = (actual_distance / kpl) * price_per_liter
    is_intercity = planned_distance > 60
    toll_cost = np.where(is_intercity, planned_distance * 850, 0)
    # Allowance harian: base kecil untuk trip lokal (last-mile intra-region),
    # naik untuk trip antar-kota jauh yang butuh bermalam. Sebelumnya flat
    # 145rb untuk SEMUA trip -- itu realistis untuk long-haul, tapi
    # membuatnya jadi ongkos dominan & murni-mengikuti-volume untuk trip
    # lokal DKI yang jaraknya cuma puluhan km, sehingga menutupi sinyal dari
    # fuel/overtime/maintenance saat volume turun.
    nights = np.clip((transit_hours - 10) // 24, 0, 5)
    allowance = np.where(is_intercity, 145000, 45000) + nights * 22000
    overtime_cost = np.clip(transit_hours - cfg.OVERTIME_THRESHOLD_HOURS, 0, None) * cfg.OVERTIME_RATE_IDR

    delivery_cost = fuel_cost + toll_cost + allowance + overtime_cost

    delivery_id = np.arange(1, n + 1)
    df = pd.DataFrame({
        "delivery_id": delivery_id,
        "order_id": deliverable.order_id.values,
        "attempt_no": 1,
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
        "dispatched_at": dispatched_at,
        "arrived_at": arrived_at,
        "delivered_at": delivered_at.values,
        "planned_distance_km": np.round(planned_distance, 2),
        "actual_distance_km": np.round(actual_distance, 2),
        "status": status,
        "failure_reason": failure_reason,
        "pod_signed": status == "delivered",
        "delivery_cost_idr": delivery_cost.astype(np.int64),
        "fuel_cost_idr": fuel_cost.astype(np.int64),
        "toll_cost_idr": toll_cost.astype(np.int64),
        "allowance_idr": allowance.astype(np.int64),
        "overtime_cost_idr": overtime_cost.astype(np.int64),
        "dest_region_code": reg_code_arr,
    })

    # [TRAP D3] ~4800 order 'delivered' mendapat reattempt kedua (percobaan pertama gagal)
    delivered_idx = df.index[df.status == "delivered"].values
    reattempt_n = min(4800, len(delivered_idx))
    reattempt_src = cfg.RNG.choice(delivered_idx, size=reattempt_n, replace=False)
    reattempt_rows = df.loc[reattempt_src].copy()
    reattempt_rows["delivery_id"] = np.arange(df.delivery_id.max() + 1, df.delivery_id.max() + 1 + reattempt_n)
    reattempt_rows["attempt_no"] = 1  # ini attempt pertama (gagal)
    reattempt_rows["status"] = "failed"
    reattempt_rows["failure_reason"] = cfg.RNG.choice(
        ["customer_closed", "address_not_found", "refused"], size=reattempt_n)
    reattempt_rows["delivered_at"] = pd.NaT
    reattempt_rows["pod_signed"] = False
    reattempt_rows["dispatched_at"] = pd.to_datetime(reattempt_rows["dispatched_at"]) - pd.to_timedelta(1, unit="D")
    # baris asli jadi attempt_no=2 (berhasil)
    df.loc[reattempt_src, "attempt_no"] = 2

    df = pd.concat([df, reattempt_rows], ignore_index=True)
    return df


# --------------------------------------------------------------- fuel_transactions
def gen_fuel_transactions(vehicles_df, drivers_df, locations_df, regions_df):
    """Odometer dibuat KONSISTEN secara fisik dengan liters yang dibeli
    (Δodometer = liters * km_per_liter_efektif), supaya jalur deteksi A01
    (LAG(odometer)/liters per model per bulan) benar-benar valid -- pada
    versi awal odometer digenerate independen dari liters sehingga rasio
    km/liter yang dihitung dari data nyaris acak (ketahuan saat verifikasi
    SQL gate 0d, bukan sekadar pandas). Region stasiun juga dipakai untuk
    FUEL_REGIONAL_FACTOR supaya konsisten dengan deliveries.fuel_cost_idr
    (sebelumnya faktor regional hanya diterapkan di tabel deliveries, tidak
    di fuel_transactions -- inkonsistensi yang juga ketahuan di gate 0d)."""
    n = cfg.N_FUEL_TX
    fuel_stations = locations_df[locations_df.loc_type == "fuel_station"]
    veh_active = vehicles_df[vehicles_df.status != "retired"].reset_index(drop=True)
    station_region = locations_df.set_index("location_id")["region_id"]
    region_code_map = regions_df.set_index("region_id")["region_code"]
    kpl_lookup = {m[0]: m[5] for m in cfg.VEHICLE_MODELS}

    veh_pick = veh_active.sample(n=n, replace=True, random_state=cfg.RANDOM_SEED).reset_index(drop=True)
    days = pd.date_range(cfg.YEAR_START, cfg.YEAR_END, freq="D")
    txn_date = days[cfg.RNG.integers(0, len(days), n)] + pd.to_timedelta(cfg.RNG.uniform(5, 22, n), unit="h")
    station_id = cfg.RNG.choice(fuel_stations.location_id.values, size=n)

    tmp = pd.DataFrame({
        "vehicle_id": veh_pick.vehicle_id.values,
        "model_code": veh_pick.model_code.values,
        "acquisition_date": veh_pick.acquisition_date.values,
        "tank_capacity_liter": veh_pick.tank_capacity_liter.values,
        "transacted_at": txn_date,
        "station_location_id": station_id,
        "driver_id": cfg.RNG.choice(drivers_df.driver_id.values, size=n),
        "payment_method": cfg.RNG.choice(["fuel_card", "cash"], size=n, p=[0.86, 0.14]),
    }).sort_values(["vehicle_id", "transacted_at"]).reset_index(drop=True)

    liters = tmp.tank_capacity_liter.values * cfg.RNG.uniform(0.45, 0.92, n)
    month = tmp.transacted_at.dt.month.values
    is_a01 = (tmp.model_code.values == cfg.A01_MODEL) & \
             (pd.to_datetime(tmp.acquisition_date) < pd.Timestamp(cfg.A01_ACQ_BEFORE)).values & \
             (month >= cfg.A01_START_MONTH)
    nominal_kpl = np.array([kpl_lookup[m] for m in tmp.model_code.values])
    kpl_eff = nominal_kpl * np.where(is_a01, 1 - cfg.A01_EFFICIENCY_DROP, 1.0) * cfg.RNG.normal(1.0, 0.06, n)
    kpl_eff = np.clip(kpl_eff, 2.0, 20.0)
    distance = liters * kpl_eff

    # odometer kumulatif per kendaraan, urut waktu -- ini yang membuat
    # Delta(odometer)/liters merefleksikan konsumsi BBM sesungguhnya
    tmp["distance"] = distance
    start_odo = cfg.RNG.uniform(500, 4000, tmp.vehicle_id.nunique())
    start_odo_map = dict(zip(tmp.vehicle_id.unique(), start_odo))
    tmp["start_odo"] = tmp.vehicle_id.map(start_odo_map)
    tmp["odometer_km"] = tmp.groupby("vehicle_id")["distance"].cumsum() + tmp["start_odo"]
    tmp["odometer_km"] = tmp["odometer_km"].astype(np.int64)

    region_id = tmp.station_location_id.map(station_region)
    region_code = region_id.map(region_code_map)
    base_price = np.array([cfg.fuel_price_for(pd.Timestamp(d)) for d in tmp.transacted_at])
    regional_factor = region_code.map(lambda c: cfg.FUEL_REGIONAL_FACTOR.get(c, 1.0)).values
    price = base_price * regional_factor
    total_cost = np.round(liters * price).astype(np.int64)

    df = pd.DataFrame({
        "fuel_id": np.arange(1, n + 1),
        "vehicle_id": tmp.vehicle_id.values,
        "driver_id": tmp.driver_id.values,
        "station_location_id": tmp.station_location_id.values,
        "transacted_at": tmp.transacted_at.values,
        "liters": np.round(liters, 2),
        "price_per_liter_idr": price.astype(np.int64),
        "total_cost_idr": total_cost,
        "odometer_km": tmp.odometer_km.values,
        "payment_method": tmp.payment_method.values,
    })

    # A06: fraud pada 18 kendaraan -> liters melebihi tank, atau transaksi ganda cepat
    fraud_vehicles = cfg.RNG.choice(veh_active.vehicle_id.values, size=cfg.A06_N_VEHICLES, replace=False)
    fraud_idx = df.index[df.vehicle_id.isin(fraud_vehicles)][:214]
    if len(fraud_idx):
        df.loc[fraud_idx, "liters"] = df.loc[fraud_idx, "vehicle_id"].map(
            veh_active.set_index("vehicle_id").tank_capacity_liter) * cfg.RNG.uniform(1.05, 1.4, len(fraud_idx))
        df.loc[fraud_idx, "total_cost_idr"] = np.round(df.loc[fraud_idx, "liters"] * df.loc[fraud_idx, "price_per_liter_idr"]).astype(np.int64)

    # A07: odometer rollback pada 7 kendaraan (beberapa baris odometer turun drastis)
    rollback_vehicles = cfg.RNG.choice(veh_active.vehicle_id.values, size=cfg.A07_N_VEHICLES, replace=False)
    for v in rollback_vehicles:
        vidx = df.index[df.vehicle_id == v]
        if len(vidx) < 3:
            continue
        vidx_sorted = df.loc[vidx].sort_values("transacted_at").index
        n_bad = max(1, len(vidx_sorted) // 6)
        bad_positions = cfg.RNG.choice(range(1, len(vidx_sorted)), size=min(n_bad, len(vidx_sorted) - 1), replace=False)
        for pos in bad_positions:
            idx = vidx_sorted[pos]
            df.loc[idx, "odometer_km"] = max(0, int(df.loc[idx, "odometer_km"] * cfg.RNG.uniform(0.3, 0.7)))

    return df


# --------------------------------------------------------------------- maintenance
def gen_maintenance(vehicles_df, locations_df, regions_df=None):
    n = cfg.N_MAINTENANCE
    workshops = locations_df[locations_df.loc_type == "workshop"]
    veh_pick = vehicles_df.sample(n=n, replace=True, random_state=cfg.RANDOM_SEED + 1).reset_index(drop=True)

    days = pd.date_range(cfg.YEAR_START, cfg.YEAR_END, freq="D")
    sched_date = days[cfg.RNG.integers(0, len(days), n)]

    mtc_type = cfg.RNG.choice(["preventive", "corrective", "inspection"], size=n, p=[0.61, 0.31, 0.08])

    workshop_region = workshops.merge(
        pd.DataFrame(cfg.REGIONS, columns=["region_id","region_code","region_name","island","lat","lon","cong"])[["region_id","region_code"]],
        on="region_id")
    a21_workshops = workshop_region[workshop_region.region_code == cfg.A21_WORKSHOP_REGION].location_id.values
    other_workshops = workshops[~workshops.location_id.isin(a21_workshops)].location_id.values

    workshop_id = cfg.RNG.choice(workshops.location_id.values, size=n)

    # A21: compliance (performed vs scheduled) turun di workshop JABAR sejak Mei
    month = sched_date.month
    is_a21_ws = np.isin(workshop_id, a21_workshops)
    compliance_p = np.where(is_a21_ws & (month >= cfg.A21_START_MONTH), cfg.A21_COMPLIANCE_AFTER,
                    np.where(is_a21_ws, cfg.A21_COMPLIANCE_BEFORE, 0.90))
    performed = cfg.RNG.random(n) < compliance_p
    lag_days = cfg.RNG.integers(0, 10, n)
    performed_date = np.where(performed, (pd.to_datetime(sched_date) + pd.to_timedelta(lag_days, unit="D")).values, np.datetime64("NaT"))

    cost = np.where(
        mtc_type == "preventive", cfg.RNG.lognormal(np.log(1_800_000), 0.35, n),
        np.where(mtc_type == "corrective", cfg.RNG.lognormal(np.log(2_600_000), 0.55, n),
                 cfg.RNG.lognormal(np.log(400_000), 0.3, n))
    )
    downtime = np.where(mtc_type == "corrective", cfg.RNG.gamma(3, 6, n), cfg.RNG.gamma(1.5, 2, n))

    df = pd.DataFrame({
        "maintenance_id": np.arange(1, n + 1),
        "vehicle_id": veh_pick.vehicle_id.values,
        "mtc_type": mtc_type,
        "scheduled_date": sched_date,
        "performed_date": performed_date,
        "odometer_km": veh_pick.odometer_km.values,
        "workshop_location_id": workshop_id,
        "cost_idr": np.where(performed, cost, np.nan),  # [TRAP D5] belum dikerjakan -> cost NULL, bukan 0
        "downtime_hours": np.round(np.where(performed, downtime, np.nan), 1),
        "notes": None,
    })

    # A05 (§6.1): kendaraan DKI yang overdue service akhirnya jebol pada Agustus
    # -> sebagian corrective maintenance yang harusnya tersebar merata digeser
    # ke Agustus, dengan biaya lebih tinggi (kerusakan yang dibiarkan makin parah).
    if regions_df is not None:
        mtc_rng = np.random.default_rng(cfg.RANDOM_SEED + 9002)  # RNG terisolasi, lihat catatan A02 di atas
        depot_region = locations_df.set_index("location_id")["region_id"]
        veh_region = vehicles_df.set_index("vehicle_id")["home_depot_id"].map(depot_region)
        dki_region_id = int(regions_df.loc[regions_df.region_code == cfg.A05_MTC_REGION, "region_id"].iloc[0])
        overdue = (vehicles_df.set_index("vehicle_id").odometer_km -
                   vehicles_df.set_index("vehicle_id").last_service_odometer_km) > \
                  (vehicles_df.set_index("vehicle_id").service_interval_km * 1.25)
        dki_overdue_vehicles = set(
            veh_region[(veh_region == dki_region_id) & overdue].index
        )
        eligible = df.index[
            (df.mtc_type == "corrective") & df.vehicle_id.isin(dki_overdue_vehicles)
        ]
        if len(eligible):
            n_bump = int(len(eligible) * cfg.A05_MTC_BUMP_SHARE)
            bump_idx = mtc_rng.choice(eligible, size=n_bump, replace=False)
            aug_dates = pd.date_range("2025-08-01", "2025-08-31")
            df.loc[bump_idx, "scheduled_date"] = mtc_rng.choice(aug_dates, size=n_bump)
            df.loc[bump_idx, "performed_date"] = df.loc[bump_idx, "scheduled_date"] + \
                pd.to_timedelta(mtc_rng.integers(0, 5, n_bump), unit="D")
            df.loc[bump_idx, "cost_idr"] = df.loc[bump_idx, "cost_idr"].fillna(2_600_000) * cfg.A05_MTC_COST_MULT

    return df


# ----------------------------------------------------------------- vehicle_events
def gen_vehicle_events(vehicles_df, drivers_df, deliveries_df, locations_df):
    n = cfg.N_VEHICLE_EVENTS
    ev_type = cfg.RNG.choice(
        ["harsh_braking", "overspeed", "idle_excess", "geofence_exit", "engine_fault", "breakdown", "accident"],
        size=n, p=[0.34, 0.26, 0.19, 0.09, 0.07, 0.04, 0.01])

    with_delivery = cfg.RNG.random(n) < 0.78
    delivery_sample = deliveries_df.sample(n=n, replace=True, random_state=cfg.RANDOM_SEED + 2).reset_index(drop=True)

    vehicle_id = np.where(with_delivery, delivery_sample.vehicle_id.values,
                           cfg.RNG.choice(vehicles_df.vehicle_id.values, size=n))
    driver_id = np.where(with_delivery, delivery_sample.driver_id.values,
                          np.where(cfg.RNG.random(n) < 0.5, cfg.RNG.choice(drivers_df.driver_id.values, size=n), None))
    delivery_id = np.where(with_delivery, delivery_sample.delivery_id.values, None)

    occurred_at = pd.to_datetime(delivery_sample.dispatched_at.values) + pd.to_timedelta(cfg.RNG.uniform(0, 8, n), unit="h")
    occurred_at = np.where(with_delivery, occurred_at,
                            pd.date_range(cfg.YEAR_START, cfg.YEAR_END, periods=n))

    severity = cfg.RNG.integers(1, 6, n)

    veh_lookup = vehicles_df.set_index("vehicle_id")
    # A03: breakdown terkonsentrasi pada kendaraan overdue service
    overdue = (veh_lookup.odometer_km - veh_lookup.last_service_odometer_km) > (veh_lookup.service_interval_km * 1.25)
    is_breakdown = ev_type == "breakdown"
    veh_overdue_flag = pd.Series(vehicle_id).map(overdue).fillna(False).values
    # perbesar peluang breakdown pada kendaraan overdue: lakukan resampling sederhana
    boost_idx = np.where(is_breakdown & ~veh_overdue_flag & (cfg.RNG.random(n) < 0.7))[0]
    overdue_vehicle_ids = veh_lookup[overdue].index.values
    if len(overdue_vehicle_ids) and len(boost_idx):
        vehicle_id[boost_idx] = cfg.RNG.choice(overdue_vehicle_ids, size=len(boost_idx))

    df = pd.DataFrame({
        "event_id": np.arange(1, n + 1),
        "vehicle_id": vehicle_id,
        "driver_id": driver_id,
        "delivery_id": delivery_id,
        "ev_type": ev_type,
        "occurred_at": occurred_at,
        "severity": severity,
        "metadata": None,
    })
    return df
