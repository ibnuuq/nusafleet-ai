"""
Entry point generator NusaFleet.
Jalankan: python main.py
Output: CSV di ../seeds/ (data/seeds/), siap di-load lewat load.py
"""
import os
import time

import pandas as pd

import config as cfg
import dimensions as dim
import facts as fct
import post_inject as pinj

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "seeds")


def save(df, name):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    print(f"  {name:<22} {len(df):>9,} rows  -> {path}")


def main():
    t0 = time.time()
    print(f"RANDOM_SEED = {cfg.RANDOM_SEED}\n")

    print("[1/9] regions")
    regions_df = dim.gen_regions()
    save(regions_df, "regions")

    print("[2/9] locations")
    locations_df, depot_ids = dim.gen_locations(regions_df)
    save(locations_df, "locations")

    print("[3/9] vehicle_models")
    vm_df = dim.gen_vehicle_models()
    save(vm_df, "vehicle_models")

    print("[4/9] vehicles")
    vehicles_df = dim.gen_vehicles(vm_df, locations_df, depot_ids)
    save(vehicles_df, "vehicles")

    print("[5/9] drivers")
    drivers_df = dim.gen_drivers(locations_df, depot_ids)
    save(drivers_df, "drivers")

    print("[6/9] customers + sla_history")
    customers_df, sla_hist_df = dim.gen_customers(regions_df, locations_df)
    save(customers_df, "customers")
    save(sla_hist_df, "customer_sla_history")

    print("[7/9] orders")
    orders_df = fct.gen_orders(customers_df, locations_df, depot_ids)
    save(orders_df, "orders")

    print("[8/9] deliveries")
    deliveries_df = fct.gen_deliveries(orders_df, vehicles_df, drivers_df, locations_df, depot_ids, regions_df)
    save(deliveries_df, "deliveries")

    print("[9/9] fuel_transactions, maintenance, vehicle_events")
    fuel_df = fct.gen_fuel_transactions(vehicles_df, drivers_df, locations_df, regions_df)
    save(fuel_df, "fuel_transactions")

    maint_df = fct.gen_maintenance(vehicles_df, locations_df, regions_df)
    save(maint_df, "maintenance")

    events_df = fct.gen_vehicle_events(vehicles_df, drivers_df, deliveries_df, locations_df)
    save(events_df, "vehicle_events")

    # ------------------------------------------------------------------
    # POST-PROCESS: 11 anomali tambahan (A04,A11,A12,A13,A14,A16,A18,A19,A20,A22,A26)
    # Tidak menyentuh fungsi generator dasar -- lihat post_inject.py
    # ------------------------------------------------------------------
    print("\n[post] injecting anomalies tambahan...")
    manifest_entries = []

    # --- correctness patch dulu (bug ketahuan saat verifikasi SQL gate 0d) ---
    orders_df, m = pinj.inject_a10_fix(orders_df, customers_df, sla_hist_df)
    manifest_entries.append(m); print("  A10_FIX done:", m)

    deliveries_df, m = pinj.inject_a23_fix(deliveries_df, orders_df, locations_df, regions_df)
    manifest_entries.append(m); print("  A23_FIX done:", m)

    locations_df, orders_df, deliveries_df, m = pinj.inject_a19(customers_df, locations_df, orders_df, deliveries_df)
    manifest_entries.append(m); print("  A19 done:", m)

    orders_df, m = pinj.inject_a20(orders_df, deliveries_df, vehicles_df, vm_df)
    manifest_entries.append(m); print("  A20 done:", m)

    deliveries_df, m = pinj.inject_a04_license_compliance(deliveries_df, vehicles_df, vm_df, drivers_df)
    manifest_entries.append(m); print("  A04_LICENSE_COMPLIANCE_FIX done:", m)

    deliveries_df, events_df, m = pinj.inject_a04(deliveries_df, vehicles_df, vm_df, drivers_df, events_df)
    manifest_entries.append(m); print("  A04 done:", m)

    maint_df, locations_df, m = pinj.inject_a11(maint_df, locations_df)
    manifest_entries.append(m); print("  A11 done:", m)

    events_df, m = pinj.inject_a12(deliveries_df, events_df, orders_df, locations_df, regions_df)
    manifest_entries.append(m); print("  A12 done:", m)

    deliveries_df, events_df, m = pinj.inject_a13(deliveries_df, events_df, locations_df)
    manifest_entries.append(m); print("  A13 done:", m)

    vehicles_df, deliveries_df, maint_df, m = pinj.inject_a16(vehicles_df, deliveries_df, maint_df)
    manifest_entries.append(m); print("  A16 done:", m)

    events_df, m = pinj.inject_a18(deliveries_df, drivers_df, events_df)
    manifest_entries.append(m); print("  A18 done:", m)

    deliveries_df, events_df, m = pinj.inject_a22(deliveries_df, events_df)
    manifest_entries.append(m); print("  A22 done:", m)

    maint_df, m = pinj.inject_a26(vehicles_df, maint_df)
    manifest_entries.append(m); print("  A26 done:", m)

    events_df, maint_df, m = pinj.inject_a14(vehicles_df, events_df, maint_df)
    manifest_entries.append(m); print("  A14 done:", m)

    # simpan ulang semua tabel yang berubah post-process
    save(locations_df, "locations")
    save(orders_df, "orders")
    save(deliveries_df, "deliveries")
    save(vehicles_df, "vehicles")
    save(maint_df, "maintenance")
    save(events_df, "vehicle_events")

    import json
    manifest_path = os.path.join(OUT_DIR, "..", "post_inject_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest_entries, f, indent=2, default=str)
    print(f"\nRaw manifest tersimpan: {manifest_path}")

    print(f"\nSelesai dalam {time.time() - t0:.1f} detik.")
    print("\nRingkasan volume:")
    for name, df in [
        ("customers", customers_df), ("drivers", drivers_df), ("vehicles", vehicles_df),
        ("locations", locations_df), ("orders", orders_df), ("deliveries", deliveries_df),
        ("fuel_transactions", fuel_df), ("maintenance", maint_df), ("vehicle_events", events_df),
    ]:
        print(f"  {name:<20} {len(df):>9,}")
    total = sum(len(d) for d in [customers_df, drivers_df, vehicles_df, locations_df,
                                  orders_df, deliveries_df, fuel_df, maint_df, events_df])
    print(f"  {'TOTAL':<20} {total:>9,}")


if __name__ == "__main__":
    main()
