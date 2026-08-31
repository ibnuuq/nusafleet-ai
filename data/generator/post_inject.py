"""
post_inject.py — injeksi anomali tahap kedua.

Prinsip: TIDAK mengubah fungsi generator dasar (dimensions.py, facts.py inti)
yang sudah tervalidasi di gate 0d putaran pertama (A01,A02,A03,A05,A06,A07,
A09,A10,A15,A21,A23,A25,D1,D3,D5,D7). Semua anomali baru diterapkan sebagai
post-process di atas DataFrame yang sudah jadi, dengan RNG terisolasi per
anomali (RANDOM_SEED + 20000 + nomor anomali) supaya menuning satu anomali
tidak menggeser anomali lain -- pelajaran dari insiden kalibrasi A05
sebelumnya.

Setiap fungsi inject_Axx mengembalikan dict `manifest_entry` berisi info yang
nanti dipakai ground-truth manifest (bukan untuk dibaca agent).
"""
import numpy as np
import pandas as pd

import config as cfg


def _rng(anomaly_no):
    return np.random.default_rng(cfg.RANDOM_SEED + 20000 + anomaly_no)


# --------------------------------------------------------------------- A10 (fix)
def inject_a10_fix(orders_df, customers_df, sla_hist_df):
    """PATCH KOREKSI (bukan anomali baru): promised_delivery_at sebelumnya
    dihitung dari customers.sla_hours SAAT INI untuk SEMUA order sepanjang
    tahun, padahal SLA platinum-FMCG baru berubah 36->24 jam per 1 Juni.
    Akibatnya breach rate sebelum/sesudah Juni nyaris sama (bug baru
    ketahuan saat verifikasi SQL gate 0d: breach_rate_before=0.018,
    after=0.022, rasio cuma 1.24x, semestinya jauh lebih tinggi).
    Perbaikan: hitung ulang promised_delivery_at HANYA untuk customer
    platinum-fmcg (A10), pakai SLA yang berlaku pada requested_pickup_at."""
    a10_customers = set(customers_df.loc[
        (customers_df.tier == "platinum") & (customers_df.segment == "fmcg"), "customer_id"])
    mask = orders_df.customer_id.isin(a10_customers)
    idx = orders_df.index[mask]
    pickup = pd.to_datetime(orders_df.loc[idx, "requested_pickup_at"])
    sla_hours = np.where(pickup < pd.Timestamp("2025-06-01"), 36, 24)
    orders_df.loc[idx, "promised_delivery_at"] = pickup + pd.to_timedelta(sla_hours, unit="h")
    return orders_df, dict(fix_id="A10_FIX", n_customers=len(a10_customers), n_orders_patched=int(mask.sum()))


# --------------------------------------------------------------------- A23 (fix)
def inject_a23_fix(deliveries_df, orders_df, locations_df, regions_df):
    """PATCH KOREKSI (bukan anomali baru): tol baru Cikampek-Palimanan (A23)
    di kode asal cuma mengurangi transit_hours, TIDAK mengurangi
    actual_distance_km -- padahal katalog menyatakan jarak juga turun ~8%.
    Ketahuan saat verifikasi SQL gate 0d (avg_distance Agu->Sep nyaris tidak
    berubah). Perbaikan: kurangi actual_distance_km ~8% untuk delivery
    tujuan JABAR sejak September, lalu sesuaikan fuel_cost & delivery_cost
    supaya tetap konsisten (fuel_cost = actual_distance/kpl * price, tapi
    kita tidak menyimpan kpl per delivery -- pendekatan: skalakan fuel_cost
    dengan rasio jarak yang sama, pendekatan wajar karena fuel_cost
    proporsional linear terhadap actual_distance_km pada formula asli)."""
    rng = _rng(23)
    loc = locations_df.set_index("location_id")
    reg = regions_df.set_index("region_id")
    d = deliveries_df.merge(orders_df[["order_id", "destination_location_id"]], on="order_id")
    dest_region_code = reg.loc[loc.loc[d.destination_location_id, "region_id"].values, "region_code"].values
    month = pd.to_datetime(d.dispatched_at).dt.month.values
    mask = (dest_region_code == "JABAR") & (month >= 9)
    idx = deliveries_df.index[mask.values] if hasattr(mask, "values") else deliveries_df.index[mask]

    factor = rng.uniform(0.90, 0.94, len(idx))  # ~8% turun rata-rata
    old_dist = deliveries_df.loc[idx, "actual_distance_km"].copy()
    deliveries_df.loc[idx, "actual_distance_km"] = (old_dist * factor).round(2)
    ratio = deliveries_df.loc[idx, "actual_distance_km"] / old_dist.replace(0, np.nan)
    ratio = ratio.fillna(1.0)
    old_fuel = deliveries_df.loc[idx, "fuel_cost_idr"].copy()
    deliveries_df.loc[idx, "fuel_cost_idr"] = (old_fuel * ratio).astype(np.int64)
    fuel_delta = deliveries_df.loc[idx, "fuel_cost_idr"] - old_fuel
    deliveries_df.loc[idx, "delivery_cost_idr"] = deliveries_df.loc[idx, "delivery_cost_idr"] + fuel_delta

    return deliveries_df, dict(fix_id="A23_FIX", n_deliveries_patched=int(len(idx)),
                                avg_distance_reduction_pct=round(float((1 - factor.mean()) * 100), 1))


# --------------------------------------------------------------------- A04 (fix dasar)
def inject_a04_license_compliance(deliveries_df, vehicles_df, vehicle_models_df, drivers_df):
    """PATCH KOREKSI (bukan anomali baru): gen_deliveries dasar menugaskan
    driver murni acak dari pool depot, TANPA mempertimbangkan lisensi sama
    sekali -- akibatnya proporsi B2/B1 yang 'salah' mengemudikan
    tronton/tractor_head sudah besar SECARA ALAMI (>40% dari seluruh delivery
    kendaraan berat), sehingga 41 driver yang sengaja dijadikan anomali A04
    tenggelam dalam noise. Ketahuan saat verifikasi SQL gate 0d (query
    generik menangkap 451 'mismatch driver' alih-alih ~41).
    Perbaikan: tegakkan dulu aturan bisnis (tronton/tractor_head seharusnya
    B2_UMUM) untuk SELURUH delivery kendaraan berat, baru anomali A04
    disuntikkan di atas populasi yang sudah patuh."""
    rng = _rng(41)  # RNG terpisah dari inject_a04 (yg pakai _rng(4))
    veh = vehicles_df.merge(vehicle_models_df[["model_id", "v_class"]], on="model_id")
    d = deliveries_df.merge(veh[["vehicle_id", "v_class"]], on="vehicle_id")
    d = d.merge(drivers_df[["driver_id", "license_type", "home_depot_id"]], on="driver_id")
    heavy_idx = deliveries_df.index[d.v_class.isin(["tronton", "tractor_head"]).values]
    noncompliant = heavy_idx[(d.loc[d.v_class.isin(["tronton", "tractor_head"]), "license_type"] != "B2_UMUM").values]

    umum_by_depot = drivers_df[drivers_df.license_type == "B2_UMUM"].groupby("home_depot_id")["driver_id"].apply(list)
    veh_depot = vehicles_df.set_index("vehicle_id")["home_depot_id"]
    n_fixed = 0
    for idx in noncompliant:
        vid = deliveries_df.at[idx, "vehicle_id"]
        depot = veh_depot.get(vid)
        pool = umum_by_depot.get(depot)
        if pool is None or len(pool) == 0:
            pool = drivers_df.loc[drivers_df.license_type == "B2_UMUM", "driver_id"].values
        deliveries_df.at[idx, "driver_id"] = pool[rng.integers(0, len(pool))]
        n_fixed += 1

    return deliveries_df, dict(fix_id="A04_LICENSE_COMPLIANCE_FIX", n_heavy_deliveries=int(len(heavy_idx)),
                                n_reassigned_to_compliant=n_fixed)


# --------------------------------------------------------------------- A19
def inject_a19(customers_df, locations_df, orders_df, deliveries_df):
    """CUST-04417: seluruh order diarahkan ke satu lokasi 'resmi' yang
    koordinatnya salah (offset ~12.4km dari lokasi customer_site asli),
    menyebabkan mayoritas delivery-nya gagal dengan address_not_found."""
    rng = _rng(19)
    target_customer_id = 4417
    cust_row = customers_df.loc[customers_df.customer_id == target_customer_id].iloc[0]
    true_loc_id = int(cust_row.primary_location_id)
    true_loc = locations_df.loc[locations_df.location_id == true_loc_id].iloc[0]

    # buat lokasi baru "tercatat" dengan offset ~12.4km ke arah acak
    bearing = rng.uniform(0, 2 * np.pi)
    dlat = (12.4 / 111.0) * np.cos(bearing)
    dlon = (12.4 / 111.0) * np.sin(bearing) / np.cos(np.radians(true_loc.lat))
    new_loc_id = int(locations_df.location_id.max()) + 1
    new_row = {
        "location_id": new_loc_id,
        "location_code": f"CS-{new_loc_id:06d}",
        "name": f"{cust_row.company_name} (recorded address)",
        "loc_type": "customer_site",
        "region_id": int(true_loc.region_id),
        "address": f"[koordinat tercatat salah, offset dari lokasi asli {true_loc.location_code}]",
        "lat": true_loc.lat + dlat,
        "lon": true_loc.lon + dlon,
    }
    locations_df = pd.concat([locations_df, pd.DataFrame([new_row])], ignore_index=True)

    order_mask = orders_df.customer_id == target_customer_id
    orders_df.loc[order_mask, "destination_location_id"] = new_loc_id
    target_order_ids = set(orders_df.loc[order_mask, "order_id"])

    deliv_mask = deliveries_df.order_id.isin(target_order_ids)
    flip_idx = deliveries_df.index[deliv_mask & (rng.random(len(deliveries_df)) < 1.0) & deliv_mask]
    # 85% dari attempt customer ini gagal address_not_found (bukan 100%, supaya tetap ada delivered)
    n = deliv_mask.sum()
    fail_flag = rng.random(n) < 0.85
    idxs = deliveries_df.index[deliv_mask]
    fail_idxs = idxs[fail_flag]
    deliveries_df.loc[fail_idxs, "status"] = "failed"
    deliveries_df.loc[fail_idxs, "failure_reason"] = "address_not_found"
    deliveries_df.loc[fail_idxs, "delivered_at"] = pd.NaT
    deliveries_df.loc[fail_idxs, "pod_signed"] = False

    manifest = dict(
        anomaly_id="A19", customer_id=target_customer_id, wrong_location_id=new_loc_id,
        true_location_id=true_loc_id, offset_km=12.4, n_deliveries_affected=int(n),
        n_failed_injected=int(fail_idxs.shape[0]),
    )
    return locations_df, orders_df, deliveries_df, manifest


# --------------------------------------------------------------------- A20
def inject_a20(orders_df, deliveries_df, vehicles_df, vehicle_models_df):
    """Tronton load factor rata-rata diturunkan ke ~41% kapasitas;
    8.1% delivery ber-vehicle CDE dibuat overload (>100% kapasitas)."""
    rng = _rng(20)
    veh = vehicles_df.merge(vehicle_models_df[["model_id", "v_class", "capacity_kg"]], on="model_id")
    dv = deliveries_df.merge(veh[["vehicle_id", "v_class", "capacity_kg"]], on="vehicle_id")
    dv = dv.merge(orders_df[["order_id", "weight_kg", "volume_m3", "declared_value_idr"]], on="order_id")

    orders_idx = orders_df.set_index("order_id")

    # --- tronton: skala weight_kg supaya rata2 load factor -> 41%
    tronton = dv[dv.v_class == "tronton"]
    if len(tronton):
        current_avg = tronton.weight_kg.mean()
        target_avg = 0.41 * tronton.capacity_kg.iloc[0]
        scale = target_avg / current_avg if current_avg > 0 else 1.0
        scale = float(np.clip(scale, 0.05, 3.0))
        oid = tronton.order_id.values
        orders_idx.loc[oid, "weight_kg"] = (orders_idx.loc[oid, "weight_kg"] * scale).round(2)
        orders_idx.loc[oid, "volume_m3"] = (orders_idx.loc[oid, "volume_m3"] * scale).round(2)
        orders_idx.loc[oid, "declared_value_idr"] = (orders_idx.loc[oid, "declared_value_idr"] * scale).astype(np.int64)
    else:
        scale = None

    # --- CDE: 8.1% delivery dibuat overload >100% kapasitas
    cde = dv[dv.v_class == "cde"]
    n_overload = int(round(len(cde) * 0.081))
    overload_orders = rng.choice(cde.order_id.values, size=min(n_overload, len(cde)), replace=False)
    cap = float(cde.capacity_kg.iloc[0])
    new_weight = cap * rng.uniform(1.03, 1.28, len(overload_orders))
    ratio = new_weight / orders_idx.loc[overload_orders, "weight_kg"].replace(0, np.nan).fillna(1.0).values
    orders_idx.loc[overload_orders, "volume_m3"] = (orders_idx.loc[overload_orders, "volume_m3"] * ratio).round(2)
    orders_idx.loc[overload_orders, "declared_value_idr"] = (orders_idx.loc[overload_orders, "declared_value_idr"] * ratio).astype(np.int64)
    orders_idx.loc[overload_orders, "weight_kg"] = new_weight.round(2)

    orders_df = orders_idx.reset_index()

    manifest = dict(
        anomaly_id="A20", tronton_scale_factor=scale, cde_overload_count=int(len(overload_orders)),
        cde_total_deliveries=int(len(cde)), cde_overload_share=round(len(overload_orders) / len(cde), 4) if len(cde) else None,
    )
    return orders_df, manifest


# --------------------------------------------------------------------- A04
def inject_a04(deliveries_df, vehicles_df, vehicle_models_df, drivers_df, vehicle_events_df):
    """41 driver lisensi B2 (bukan B2_UMUM) ditugaskan berulang ke kendaraan
    tronton/tractor_head -> failure rate & harsh_braking rate lebih tinggi."""
    rng = _rng(4)
    veh = vehicles_df.merge(vehicle_models_df[["model_id", "v_class"]], on="model_id")
    heavy_vehicle_ids = set(veh.loc[veh.v_class.isin(["tronton", "tractor_head"]), "vehicle_id"])

    d = deliveries_df.merge(veh[["vehicle_id", "v_class"]], on="vehicle_id")
    heavy_idx_all = deliveries_df.index[d.v_class.isin(["tronton", "tractor_head"])]

    b2_drivers = drivers_df.loc[drivers_df.license_type == "B2", "driver_id"].values
    mismatch_drivers = rng.choice(b2_drivers, size=41, replace=False)

    n_reassign = min(len(heavy_idx_all), 41 * 35)
    reassign_idx = rng.choice(heavy_idx_all, size=n_reassign, replace=False)
    assigned_driver = rng.choice(mismatch_drivers, size=n_reassign)
    deliveries_df.loc[reassign_idx, "driver_id"] = assigned_driver

    # baseline: heavy-class deliveries yang TIDAK direassign
    baseline_idx = np.setdiff1d(heavy_idx_all, reassign_idx)
    baseline_fail_rate = (deliveries_df.loc[baseline_idx, "status"].isin(["failed", "returned"])).mean()
    target_fail_rate = min(baseline_fail_rate * 3.2, 0.65)

    current_fail = deliveries_df.loc[reassign_idx, "status"].isin(["failed", "returned"])
    n_need_more_fail = int(target_fail_rate * n_reassign) - int(current_fail.sum())
    if n_need_more_fail > 0:
        delivered_pool = reassign_idx[(~current_fail.values) &
                                       (deliveries_df.loc[reassign_idx, "status"] == "delivered").values]
        flip = rng.choice(delivered_pool, size=min(n_need_more_fail, len(delivered_pool)), replace=False)
        deliveries_df.loc[flip, "status"] = "failed"
        deliveries_df.loc[flip, "failure_reason"] = rng.choice(
            ["vehicle_breakdown", "document_issue", "refused"], size=len(flip))
        deliveries_df.loc[flip, "delivered_at"] = pd.NaT
        deliveries_df.loc[flip, "pod_signed"] = False

    actual_fail_rate = (deliveries_df.loc[reassign_idx, "status"].isin(["failed", "returned"])).mean()

    # harsh_braking: baseline rate per delivery utk heavy-class non-reassign
    hb = vehicle_events_df[vehicle_events_df.ev_type == "harsh_braking"]
    baseline_hb_rate = hb.delivery_id.isin(deliveries_df.loc[baseline_idx, "delivery_id"]).sum() / max(len(baseline_idx), 1)
    target_hb_count = min(target_fail_rate * 0 + baseline_hb_rate * 2.4 * n_reassign, n_reassign * 2)
    current_hb_count = hb.delivery_id.isin(deliveries_df.loc[reassign_idx, "delivery_id"]).sum()
    n_need_hb = int(target_hb_count - current_hb_count)
    if n_need_hb > 0:
        sample_deliv = deliveries_df.loc[reassign_idx].sample(n=n_need_hb, replace=True, random_state=rng.integers(1e9))
        new_events = pd.DataFrame({
            "event_id": np.arange(vehicle_events_df.event_id.max() + 1, vehicle_events_df.event_id.max() + 1 + n_need_hb),
            "vehicle_id": sample_deliv.vehicle_id.values,
            "driver_id": sample_deliv.driver_id.values,
            "delivery_id": sample_deliv.delivery_id.values,
            "ev_type": "harsh_braking",
            "occurred_at": pd.to_datetime(sample_deliv.dispatched_at.values) + pd.to_timedelta(rng.uniform(0, 3, n_need_hb), unit="h"),
            "severity": rng.integers(2, 6, n_need_hb),
            "metadata": None,
        })
        vehicle_events_df = pd.concat([vehicle_events_df, new_events], ignore_index=True)

    actual_hb_count = vehicle_events_df[(vehicle_events_df.ev_type == "harsh_braking") &
                                         vehicle_events_df.delivery_id.isin(deliveries_df.loc[reassign_idx, "delivery_id"])].shape[0]
    actual_hb_rate = actual_hb_count / max(n_reassign, 1)

    manifest = dict(
        anomaly_id="A04", n_mismatch_drivers=41, n_reassigned_deliveries=int(n_reassign),
        baseline_fail_rate=round(float(baseline_fail_rate), 4), actual_fail_rate=round(float(actual_fail_rate), 4),
        fail_ratio=round(float(actual_fail_rate / baseline_fail_rate), 2) if baseline_fail_rate > 0 else None,
        baseline_hb_rate=round(float(baseline_hb_rate), 4), actual_hb_rate=round(float(actual_hb_rate), 4),
        hb_ratio=round(float(actual_hb_rate / baseline_hb_rate), 2) if baseline_hb_rate > 0 else None,
        mismatch_driver_ids=[int(x) for x in mismatch_drivers],
    )
    return deliveries_df, vehicle_events_df, manifest


# --------------------------------------------------------------------- A11
def inject_a11(maintenance_df, locations_df):
    """Workshop WS-07: repeat repair kendaraan sama dalam <=14 hari -> ~23%
    vs baseline armada lain."""
    rng = _rng(11)
    workshops = locations_df[locations_df.loc_type == "workshop"].sort_values("location_id").reset_index(drop=True)
    target_ws = workshops.iloc[6]  # workshop ke-7
    locations_df.loc[locations_df.location_id == target_ws.location_id, "location_code"] = "WS-07"
    locations_df.loc[locations_df.location_id == target_ws.location_id, "name"] = "Workshop WS-07"
    target_ws_id = int(target_ws.location_id)

    ws_rows = maintenance_df[maintenance_df.workshop_location_id == target_ws_id]
    n_boost = int(len(ws_rows) * 0.30)  # target ~23% dihitung dari total termasuk baris baru
    seed_rows = ws_rows.sample(n=min(n_boost, len(ws_rows)), replace=False, random_state=rng.integers(1e9))

    new_rows = []
    next_id = int(maintenance_df.maintenance_id.max()) + 1
    for _, r in seed_rows.iterrows():
        gap_days = int(rng.integers(3, 14))
        sched = pd.Timestamp(r.scheduled_date) + pd.Timedelta(days=gap_days)
        if sched > pd.Timestamp("2025-12-31"):
            continue
        new_rows.append(dict(
            maintenance_id=next_id, vehicle_id=r.vehicle_id, mtc_type="corrective",
            scheduled_date=sched.date(), performed_date=(sched + pd.Timedelta(days=int(rng.integers(0, 3)))).date(),
            odometer_km=r.odometer_km, workshop_location_id=target_ws_id,
            cost_idr=float(rng.lognormal(np.log(2_200_000), 0.4)), downtime_hours=round(float(rng.gamma(2, 4)), 1),
            notes="repeat_repair",
        ))
        next_id += 1
    if new_rows:
        maintenance_df = pd.concat([maintenance_df, pd.DataFrame(new_rows)], ignore_index=True)

    manifest = dict(anomaly_id="A11", workshop_location_id=target_ws_id, workshop_code="WS-07",
                     n_repeat_rows_injected=len(new_rows))
    return maintenance_df, locations_df, manifest


# --------------------------------------------------------------------- A12
def inject_a12(deliveries_df, vehicle_events_df, orders_df, locations_df, regions_df):
    """Musim hujan (Des-Feb) koridor Semarang<->Surabaya -> accident event 2.8x."""
    rng = _rng(12)
    loc = locations_df.set_index("location_id")
    reg = regions_df.set_index("region_id")

    d = deliveries_df.merge(orders_df[["order_id", "origin_location_id", "destination_location_id"]], on="order_id")
    origin_code = loc.loc[d.origin_location_id, "location_code"].values
    dest_region = loc.loc[d.destination_location_id, "region_id"].values
    dest_region_code = reg.loc[dest_region, "region_code"].values
    month = pd.to_datetime(d.dispatched_at).dt.month.values

    corridor_mask = np.isin(origin_code, ["JTG-01", "JTM-01"]) & np.isin(dest_region_code, ["JATENG", "JATIM"])
    rainy_mask = np.isin(month, [12, 1, 2])
    target_mask = corridor_mask & rainy_mask
    baseline_mask = corridor_mask & ~rainy_mask

    acc = vehicle_events_df[vehicle_events_df.ev_type == "accident"]
    target_delivery_ids = d.loc[target_mask, "delivery_id"].values
    baseline_delivery_ids = d.loc[baseline_mask, "delivery_id"].values

    baseline_rate = acc.delivery_id.isin(baseline_delivery_ids).sum() / max(len(baseline_delivery_ids), 1)
    target_count = int(round(baseline_rate * 2.8 * len(target_delivery_ids)))
    current_count = acc.delivery_id.isin(target_delivery_ids).sum()
    n_need = target_count - current_count

    if n_need > 0 and len(target_delivery_ids) > 0:
        sample_ids = rng.choice(target_delivery_ids, size=n_need, replace=True)
        sample_deliv = deliveries_df.set_index("delivery_id").loc[sample_ids].reset_index()
        new_events = pd.DataFrame({
            "event_id": np.arange(vehicle_events_df.event_id.max() + 1, vehicle_events_df.event_id.max() + 1 + n_need),
            "vehicle_id": sample_deliv.vehicle_id.values,
            "driver_id": sample_deliv.driver_id.values,
            "delivery_id": sample_deliv.delivery_id.values,
            "ev_type": "accident",
            "occurred_at": pd.to_datetime(sample_deliv.dispatched_at.values) + pd.to_timedelta(rng.uniform(0, 5, n_need), unit="h"),
            "severity": rng.integers(2, 6, n_need),
            "metadata": None,
        })
        vehicle_events_df = pd.concat([vehicle_events_df, new_events], ignore_index=True)

    actual_count = vehicle_events_df[(vehicle_events_df.ev_type == "accident") &
                                      vehicle_events_df.delivery_id.isin(target_delivery_ids)].shape[0]
    actual_rate = actual_count / max(len(target_delivery_ids), 1)

    manifest = dict(anomaly_id="A12", n_corridor_rainy_deliveries=int(len(target_delivery_ids)),
                     baseline_accident_rate=round(float(baseline_rate), 5), actual_accident_rate=round(float(actual_rate), 5),
                     ratio=round(float(actual_rate / baseline_rate), 2) if baseline_rate > 0 else None)
    return vehicle_events_df, manifest


# --------------------------------------------------------------------- A13
def inject_a13(deliveries_df, vehicle_events_df, locations_df):
    """3 rest area menyerap idle_excess panjang -> +47 menit rata2 delivery
    yang melewatinya (dibakukan lewat pergeseran delivered_at/arrived_at)."""
    rng = _rng(13)
    rest_areas = locations_df[locations_df.loc_type == "rest_area"].sort_values("location_id").reset_index(drop=True)
    chosen = rest_areas.iloc[[2, 9, 16]]  # 3 rest area tetap (deterministik dari urutan generate)
    chosen_ids = chosen.location_id.tolist()

    delivered = deliveries_df[(deliveries_df.status == "delivered") & deliveries_df.delivered_at.notna()]
    flag_n = int(len(delivered) * 0.04)
    flag_idx = rng.choice(delivered.index.values, size=flag_n, replace=False)

    extra_minutes = rng.normal(47, 9, flag_n).clip(15, 90)
    delta = pd.to_timedelta(extra_minutes, unit="m")
    deliveries_df.loc[flag_idx, "delivered_at"] = pd.to_datetime(deliveries_df.loc[flag_idx, "delivered_at"]) + delta
    has_arrived = deliveries_df.loc[flag_idx, "arrived_at"].notna()
    arr_idx = deliveries_df.loc[flag_idx].index[has_arrived]
    deliveries_df.loc[arr_idx, "arrived_at"] = pd.to_datetime(deliveries_df.loc[arr_idx, "arrived_at"]) + \
        pd.to_timedelta(extra_minutes[has_arrived.values], unit="m")

    rest_area_choice = rng.choice(chosen_ids, size=flag_n)
    flagged_deliv = deliveries_df.loc[flag_idx]
    new_events = pd.DataFrame({
        "event_id": np.arange(vehicle_events_df.event_id.max() + 1, vehicle_events_df.event_id.max() + 1 + flag_n),
        "vehicle_id": flagged_deliv.vehicle_id.values,
        "driver_id": flagged_deliv.driver_id.values,
        "delivery_id": flagged_deliv.delivery_id.values,
        "ev_type": "idle_excess",
        "occurred_at": pd.to_datetime(flagged_deliv.dispatched_at.values) + pd.to_timedelta(rng.uniform(1, 6, flag_n), unit="h"),
        "severity": rng.integers(1, 4, flag_n),
        "metadata": [f'{{"rest_area_location_id": {rid}, "idle_minutes": {m:.0f}}}' for rid, m in zip(rest_area_choice, extra_minutes)],
        "_rest_area_location_id": rest_area_choice,
    })
    vehicle_events_df = pd.concat([vehicle_events_df, new_events.drop(columns=["_rest_area_location_id"])], ignore_index=True)

    manifest = dict(anomaly_id="A13", rest_area_location_ids=[int(x) for x in chosen_ids],
                     n_flagged_deliveries=int(flag_n), avg_extra_minutes=round(float(extra_minutes.mean()), 1))
    return deliveries_df, vehicle_events_df, manifest


# --------------------------------------------------------------------- A16
def inject_a16(vehicles_df, deliveries_df, maintenance_df):
    """2 kendaraan tercatat delivery selama periode maintenance overlap
    dengan status in_maintenance -> 44 delivery total."""
    rng = _rng(16)
    candidates = vehicles_df.loc[vehicles_df.status == "active", "vehicle_id"].values
    target_vehicles = rng.choice(candidates, size=2, replace=False)

    windows = [("2025-08-04", "2025-08-24"), ("2025-11-02", "2025-11-19")]
    next_mtc_id = int(maintenance_df.maintenance_id.max()) + 1
    new_mtc_rows = []
    total_flagged = 0
    for vid, (start, end) in zip(target_vehicles, windows):
        vehicles_df.loc[vehicles_df.vehicle_id == vid, "status"] = "in_maintenance"
        new_mtc_rows.append(dict(
            maintenance_id=next_mtc_id, vehicle_id=vid, mtc_type="corrective",
            scheduled_date=start, performed_date=end,
            odometer_km=int(vehicles_df.loc[vehicles_df.vehicle_id == vid, "odometer_km"].iloc[0]),
            workshop_location_id=None, cost_idr=float(rng.lognormal(np.log(4_500_000), 0.3)),
            downtime_hours=float((pd.Timestamp(end) - pd.Timestamp(start)).total_seconds() / 3600),
            notes="A16_overlap_window",
        ))
        next_mtc_id += 1

        veh_deliv = deliveries_df.index[deliveries_df.vehicle_id == vid]
        n_target = 22
        if len(veh_deliv) >= n_target:
            pick = rng.choice(veh_deliv, size=n_target, replace=False)
        else:
            pick = veh_deliv
            extra_needed = n_target - len(veh_deliv)
            other = rng.choice(deliveries_df.index.difference(veh_deliv), size=extra_needed, replace=False)
            deliveries_df.loc[other, "vehicle_id"] = vid
            pick = np.concatenate([pick, other])

        window_days = pd.date_range(start, end, freq="D")
        new_dispatch = rng.choice(window_days, size=len(pick)) + pd.to_timedelta(rng.uniform(6, 20, len(pick)), unit="h")
        shift = pd.to_datetime(new_dispatch).values - pd.to_datetime(deliveries_df.loc[pick, "dispatched_at"]).values
        deliveries_df.loc[pick, "dispatched_at"] = new_dispatch
        for col in ["arrived_at", "delivered_at"]:
            has_val = deliveries_df.loc[pick, col].notna()
            idxs = np.array(pick)[has_val.values]
            deliveries_df.loc[idxs, col] = pd.to_datetime(deliveries_df.loc[idxs, col]) + \
                pd.to_timedelta(shift[has_val.values])
        total_flagged += len(pick)

    maintenance_df = pd.concat([maintenance_df, pd.DataFrame(new_mtc_rows)], ignore_index=True)

    manifest = dict(anomaly_id="A16", vehicle_ids=[int(x) for x in target_vehicles],
                     windows=windows, n_deliveries_flagged=int(total_flagged))
    return vehicles_df, deliveries_df, maintenance_df, manifest


# --------------------------------------------------------------------- A18
def inject_a18(deliveries_df, drivers_df, vehicle_events_df):
    """Driver dengan total jam kerja >11 jam dalam sehari -> insiden hari
    berikutnya naik ~3.1x."""
    rng = _rng(18)
    d = deliveries_df.copy()
    d["work_date"] = pd.to_datetime(d.dispatched_at).dt.date
    d["duration_h"] = (pd.to_datetime(d.arrived_at) - pd.to_datetime(d.dispatched_at)).dt.total_seconds() / 3600
    d = d[d.duration_h.notna() & (d.duration_h > 0)]

    daily = d.groupby(["driver_id", "work_date"])["duration_h"].sum().reset_index()
    overwork = daily[daily.duration_h > 11]
    overwork_pairs = set(zip(overwork.driver_id, overwork.work_date))

    d["next_date"] = d.work_date.apply(lambda x: x)  # placeholder, computed below
    d["prev_date_key"] = list(zip(d.driver_id, d.work_date - pd.Timedelta(days=1)))
    nextday_mask = d.prev_date_key.isin(overwork_pairs)
    nextday_delivery_ids = d.loc[nextday_mask, "delivery_id"].values
    other_delivery_ids = d.loc[~nextday_mask, "delivery_id"].values

    incident_types = ["harsh_braking", "overspeed", "accident"]
    ev = vehicle_events_df[vehicle_events_df.ev_type.isin(incident_types)]
    baseline_rate = ev.delivery_id.isin(other_delivery_ids).sum() / max(len(other_delivery_ids), 1)
    target_count = int(round(baseline_rate * 3.1 * len(nextday_delivery_ids)))
    current_count = ev.delivery_id.isin(nextday_delivery_ids).sum()
    n_need = target_count - current_count

    if n_need > 0 and len(nextday_delivery_ids) > 0:
        sample_ids = rng.choice(nextday_delivery_ids, size=n_need, replace=True)
        sample_deliv = deliveries_df.set_index("delivery_id").loc[sample_ids].reset_index()
        new_events = pd.DataFrame({
            "event_id": np.arange(vehicle_events_df.event_id.max() + 1, vehicle_events_df.event_id.max() + 1 + n_need),
            "vehicle_id": sample_deliv.vehicle_id.values,
            "driver_id": sample_deliv.driver_id.values,
            "delivery_id": sample_deliv.delivery_id.values,
            "ev_type": rng.choice(["harsh_braking", "overspeed"], size=n_need, p=[0.6, 0.4]),
            "occurred_at": pd.to_datetime(sample_deliv.dispatched_at.values) + pd.to_timedelta(rng.uniform(0, 4, n_need), unit="h"),
            "severity": rng.integers(2, 6, n_need),
            "metadata": None,
        })
        vehicle_events_df = pd.concat([vehicle_events_df, new_events], ignore_index=True)

    ev2 = vehicle_events_df[vehicle_events_df.ev_type.isin(incident_types)]
    actual_count = ev2.delivery_id.isin(nextday_delivery_ids).sum()
    actual_rate = actual_count / max(len(nextday_delivery_ids), 1)

    manifest = dict(anomaly_id="A18", n_overwork_driver_days=int(len(overwork_pairs)),
                     n_nextday_deliveries=int(len(nextday_delivery_ids)),
                     baseline_incident_rate=round(float(baseline_rate), 5), actual_incident_rate=round(float(actual_rate), 5),
                     ratio=round(float(actual_rate / baseline_rate), 2) if baseline_rate > 0 else None)
    return vehicle_events_df, manifest


# --------------------------------------------------------------------- A22
def inject_a22(deliveries_df, vehicle_events_df):
    """Delivery malam (dispatch 22:00-04:00): fuel cost +9% (overspeed),
    transit -12% sudah otomatis dari tod_factor di facts.py (tidak diubah)."""
    rng = _rng(22)
    hour = pd.to_datetime(deliveries_df.dispatched_at).dt.hour
    night_mask = (hour >= 22) | (hour <= 4)
    night_idx = deliveries_df.index[night_mask]

    bump = 1.09
    old_fuel = deliveries_df.loc[night_idx, "fuel_cost_idr"].copy()
    deliveries_df.loc[night_idx, "fuel_cost_idr"] = (old_fuel * bump).astype(np.int64)
    fuel_delta = deliveries_df.loc[night_idx, "fuel_cost_idr"] - old_fuel
    deliveries_df.loc[night_idx, "delivery_cost_idr"] = deliveries_df.loc[night_idx, "delivery_cost_idr"] + fuel_delta

    n_events = int(len(night_idx) * 0.18)
    sample_idx = rng.choice(night_idx, size=n_events, replace=False)
    sample_deliv = deliveries_df.loc[sample_idx]
    new_events = pd.DataFrame({
        "event_id": np.arange(vehicle_events_df.event_id.max() + 1, vehicle_events_df.event_id.max() + 1 + n_events),
        "vehicle_id": sample_deliv.vehicle_id.values,
        "driver_id": sample_deliv.driver_id.values,
        "delivery_id": sample_deliv.delivery_id.values,
        "ev_type": "overspeed",
        "occurred_at": pd.to_datetime(sample_deliv.dispatched_at.values) + pd.to_timedelta(rng.uniform(0, 3, n_events), unit="h"),
        "severity": rng.integers(2, 5, n_events),
        "metadata": None,
    })
    vehicle_events_df = pd.concat([vehicle_events_df, new_events], ignore_index=True)

    manifest = dict(anomaly_id="A22", n_night_deliveries=int(len(night_idx)), fuel_bump_pct=9.0,
                     n_overspeed_events_added=n_events)
    return deliveries_df, vehicle_events_df, manifest


# --------------------------------------------------------------------- A26
def inject_a26(vehicles_df, maintenance_df):
    """Kendaraan umur >7 tahun: biaya maintenance/km naik ~2.1x vs <3 tahun."""
    ref_date = pd.Timestamp("2025-12-31")
    age_years = (ref_date - pd.to_datetime(vehicles_df.acquisition_date)).dt.days / 365.25
    veh_age = vehicles_df.assign(age_years=age_years).set_index("vehicle_id")["age_years"]

    m = maintenance_df.merge(veh_age.rename("age_years"), left_on="vehicle_id", right_index=True)
    young_rate = (m.loc[m.age_years < 3, "cost_idr"].sum() / max(m.loc[m.age_years < 3].shape[0], 1))
    old_mask_df = m.age_years > 7
    old_idx = m.index[old_mask_df]

    target_mult = 2.1
    maintenance_df.loc[old_idx, "cost_idr"] = maintenance_df.loc[old_idx, "cost_idr"] * target_mult

    m2 = maintenance_df.merge(veh_age.rename("age_years"), left_on="vehicle_id", right_index=True)
    old_rate = m2.loc[m2.age_years > 7, "cost_idr"].sum() / max((m2.age_years > 7).sum(), 1)
    young_rate2 = m2.loc[m2.age_years < 3, "cost_idr"].sum() / max((m2.age_years < 3).sum(), 1)

    manifest = dict(anomaly_id="A26", n_old_vehicle_records=int(len(old_idx)), target_multiplier=target_mult,
                     baseline_young_avg_cost=round(float(young_rate2), 0), actual_old_avg_cost=round(float(old_rate), 0),
                     ratio=round(float(old_rate / young_rate2), 2) if young_rate2 > 0 else None)
    return maintenance_df, manifest


# --------------------------------------------------------------------- A14
def inject_a14(vehicles_df, vehicle_events_df, maintenance_df):
    """Kendaraan dengan >8 harsh_braking/1000km -> biaya maintenance/km +40%.
    Dijalankan PALING TERAKHIR supaya menghitung count harsh_braking final
    (setelah A04/A12/A13/A18/A22 menambah event)."""
    rng = _rng(14)
    hb = vehicle_events_df[vehicle_events_df.ev_type == "harsh_braking"]
    hb_count = hb.groupby("vehicle_id").size()
    odo = vehicles_df.set_index("vehicle_id")["odometer_km"]
    hb_rate = (hb_count / (odo / 1000.0)).dropna()

    high_natural = set(hb_rate[hb_rate > 8].index)
    # pastikan ada kelompok yang jelas di atas ambang: boost tambahan pada 60 kendaraan terpilih
    pool = vehicles_df.loc[~vehicles_df.vehicle_id.isin(high_natural), "vehicle_id"].values
    boosted = rng.choice(pool, size=min(60, len(pool)), replace=False)

    new_events = []
    next_id = int(vehicle_events_df.event_id.max()) + 1
    for vid in boosted:
        current = int(hb_count.get(vid, 0))
        need_rate = 8.5  # target > 8/1000km
        need_count = int(np.ceil(need_rate * odo.get(vid, 60000) / 1000.0)) - current
        for _ in range(max(need_count, 0)):
            new_events.append(dict(
                event_id=next_id, vehicle_id=vid, driver_id=None, delivery_id=None,
                ev_type="harsh_braking", occurred_at=pd.Timestamp("2025-01-01") + pd.Timedelta(days=int(rng.integers(0, 365))),
                severity=int(rng.integers(2, 5)), metadata=None,
            ))
            next_id += 1
    if new_events:
        vehicle_events_df = pd.concat([vehicle_events_df, pd.DataFrame(new_events)], ignore_index=True)

    hb2 = vehicle_events_df[vehicle_events_df.ev_type == "harsh_braking"].groupby("vehicle_id").size()
    hb_rate2 = (hb2 / (odo / 1000.0)).dropna()
    high_final = set(hb_rate2[hb_rate2 > 8].index)

    m = maintenance_df.merge(odo.rename("odometer_km_veh"), left_on="vehicle_id", right_index=True)
    low_group = m[~m.vehicle_id.isin(high_final)]
    baseline_cost_per_km = low_group.cost_idr.sum() / max(low_group.odometer_km_veh.sum(), 1)

    high_idx = maintenance_df.index[maintenance_df.vehicle_id.isin(high_final)]
    maintenance_df.loc[high_idx, "cost_idr"] = maintenance_df.loc[high_idx, "cost_idr"] * 1.4

    m2 = maintenance_df.merge(odo.rename("odometer_km_veh"), left_on="vehicle_id", right_index=True)
    high_group2 = m2[m2.vehicle_id.isin(high_final)]
    actual_cost_per_km = high_group2.cost_idr.sum() / max(high_group2.odometer_km_veh.sum(), 1)

    manifest = dict(anomaly_id="A14", n_high_hb_vehicles=len(high_final), n_boosted_vehicles=len(boosted),
                     baseline_cost_per_km=round(float(baseline_cost_per_km), 2),
                     actual_cost_per_km_high_group=round(float(actual_cost_per_km), 2),
                     ratio=round(float(actual_cost_per_km / baseline_cost_per_km), 2) if baseline_cost_per_km > 0 else None)
    return vehicle_events_df, maintenance_df, manifest
